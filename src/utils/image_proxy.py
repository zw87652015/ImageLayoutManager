import os
import hashlib
from collections import OrderedDict
from PIL import Image
from PyQt6.QtGui import QImage, QPixmap, QPainter
from PyQt6.QtCore import QObject, pyqtSignal, QRunnable, QThreadPool, Qt, QSize
from PyQt6.QtSvg import QSvgRenderer

# Supported vector formats
VECTOR_EXTENSIONS = {'.svg', '.pdf', '.eps'}
# Raster formats handled by PIL
RASTER_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.tif', '.tiff', '.bmp', '.gif', '.webp'}

def is_vector_image(path: str) -> bool:
    """Check if file is a supported vector format."""
    ext = os.path.splitext(path)[1].lower()
    return ext in VECTOR_EXTENSIONS

def is_supported_image(path: str) -> bool:
    """Check if file is a supported image format."""
    ext = os.path.splitext(path)[1].lower()
    return ext in VECTOR_EXTENSIONS or ext in RASTER_EXTENSIONS

class ThumbnailWorker(QRunnable):
    def __init__(self, path, max_size, callback, svg_override_bytes=None):
        super().__init__()
        self.path = path
        self.max_size = max_size
        self.callback = callback
        self.svg_override_bytes = svg_override_bytes
        self.setAutoDelete(True)

    def run(self):
        try:
            ext = os.path.splitext(self.path)[1].lower()

            if ext == '.svg':
                # Handle SVG vector format
                qimage = self._load_svg()
            elif ext in ('.pdf', '.eps'):
                # Handle PDF/EPS format via PyMuPDF
                qimage = self._load_pdf()
            else:
                # Handle raster formats with PIL
                qimage = self._load_raster()
            
            self.callback(self.path, qimage)
        except Exception as e:
            print(f"Error loading thumbnail for {self.path}: {e}")
            self.callback(self.path, QImage())
    
    def _load_svg(self) -> QImage:
        """Load SVG and render to QImage at appropriate size."""
        if self.svg_override_bytes:
            from PyQt6.QtCore import QByteArray
            renderer = QSvgRenderer(QByteArray(self.svg_override_bytes))
        else:
            renderer = QSvgRenderer(self.path)
        if not renderer.isValid():
            return QImage()
        
        # Get default size and scale to fit max_size
        default_size = renderer.defaultSize()
        if default_size.isEmpty():
            # Fallback if no default size
            default_size = QSize(self.max_size, self.max_size)
        
        # Scale to fit within max_size while preserving aspect ratio
        scale = min(self.max_size / default_size.width(), 
                    self.max_size / default_size.height())
        render_size = QSize(int(default_size.width() * scale),
                           int(default_size.height() * scale))
        
        # Create image with transparency
        qimage = QImage(render_size, QImage.Format.Format_ARGB32)
        qimage.fill(Qt.GlobalColor.transparent)
        
        # Render SVG
        painter = QPainter(qimage)
        renderer.render(painter)
        painter.end()
        
        return qimage
    
    def _load_pdf(self) -> QImage:
        """Load first page of PDF and render to QImage."""
        try:
            import fitz  # PyMuPDF
        except ImportError:
            print("PyMuPDF (fitz) not installed. Install with: pip install PyMuPDF")
            return QImage()
        
        doc = fitz.open(self.path)
        if doc.page_count == 0:
            doc.close()
            return QImage()
        
        page = doc[0]  # First page
        
        # Calculate zoom to fit max_size while maintaining aspect ratio
        rect = page.rect
        zoom = min(self.max_size / rect.width, self.max_size / rect.height)
        matrix = fitz.Matrix(zoom, zoom)
        
        # Render page to pixmap
        pix = page.get_pixmap(matrix=matrix, alpha=True)
        doc.close()
        
        # Convert to QImage
        qimage = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format.Format_RGBA8888)
        return qimage.copy()

    def _load_raster(self) -> QImage:
        """Load raster image with PIL."""
        with Image.open(self.path) as img:
            img.thumbnail((self.max_size, self.max_size), Image.Resampling.LANCZOS)
            
            # Convert to RGBA for Qt
            if img.mode != 'RGBA':
                img = img.convert('RGBA')
            
            data = img.tobytes("raw", "RGBA")
            qimage = QImage(data, img.width, img.height, QImage.Format.Format_RGBA8888)
            # Deep copy to ensure ownership
            return qimage.copy()

class ImageProxy(QObject):
    """
    Manages loading and caching of image thumbnails to ensure high performance.
    Uses LRU cache with bounded size and thread pool for concurrent loading.
    """
    thumbnail_ready = pyqtSignal(str) # path

    def __init__(self, max_cache_items=100):
        super().__init__()
        self._cache = OrderedDict() # path -> QPixmap, LRU ordered
        self._max_cache_items = max_cache_items
        self._loading = set() # paths currently loading
        self._max_size = 1024 # Max dimension for thumbnail
        self._thread_pool = QThreadPool.globalInstance()
        self._thread_pool.setMaxThreadCount(4)  # Limit concurrent image loads
        self._svg_overrides = {}  # path -> bytes (pre-computed modified SVG)

    def shutdown(self):
        # Wait for all workers to finish
        self._thread_pool.waitForDone(2000)
        self._loading.clear()

    def clear_cache(self):
        """Clear all cached thumbnails to force reload from disk."""
        self._cache.clear()
        self._loading.clear()

    def invalidate(self, path: str):
        """Drop a single cached entry so the next get_pixmap reloads from disk."""
        if not path:
            return
        self._cache.pop(path, None)
        self._loading.discard(path)

    def set_svg_override(self, path: str, content: bytes):
        """Set pre-computed modified SVG bytes for a path and invalidate its cache entry."""
        self._svg_overrides[path] = content
        self._cache.pop(path, None)
        self._loading.discard(path)

    def clear_svg_overrides(self):
        """Remove all SVG overrides and invalidate their cache entries."""
        for path in self._svg_overrides:
            self._cache.pop(path, None)
            self._loading.discard(path)
        self._svg_overrides.clear()

    def get_pixmap(self, path: str) -> QPixmap:
        """
        Returns a cached QPixmap if available.
        If not, returns None (or placeholder) and triggers background loading.
        Uses LRU eviction when cache is full.
        """
        if not path or not os.path.exists(path):
            return None
            
        if path in self._cache:
            # Move to end (most recently used)
            self._cache.move_to_end(path)
            return self._cache[path]
            
        if path not in self._loading:
            self._start_loading(path)
            
        return None 

    def _start_loading(self, path):
        self._loading.add(path)
        override = self._svg_overrides.get(path)
        worker = ThumbnailWorker(path, self._max_size, self._on_thumbnail_finished, override)
        self._thread_pool.start(worker)

    def _on_thumbnail_finished(self, path, qimage):
        if not qimage.isNull():
            pixmap = QPixmap.fromImage(qimage)
            
            # Evict oldest item if cache is full (LRU)
            if len(self._cache) >= self._max_cache_items:
                self._cache.popitem(last=False)  # Remove oldest (first) item
            
            self._cache[path] = pixmap
            
        if path in self._loading:
            self._loading.remove(path)
            
        self.thumbnail_ready.emit(path)

# Global instance
_instance = None

def get_image_proxy():
    global _instance
    if _instance is None:
        _instance = ImageProxy()
    return _instance
