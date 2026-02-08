import os
import hashlib
from PIL import Image
from PyQt6.QtGui import QImage, QPixmap, QPainter
from PyQt6.QtCore import QObject, pyqtSignal, QThread, Qt, QSize
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

class ThumbnailWorker(QObject):
    finished = pyqtSignal(str, QImage) # path, qimage

    def __init__(self, path, max_size):
        super().__init__()
        self.path = path
        self.max_size = max_size

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
            
            self.finished.emit(self.path, qimage)
        except Exception as e:
            print(f"Error loading thumbnail for {self.path}: {e}")
            self.finished.emit(self.path, QImage())
    
    def _load_svg(self) -> QImage:
        """Load SVG and render to QImage at appropriate size."""
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
    """
    thumbnail_ready = pyqtSignal(str) # path

    def __init__(self):
        super().__init__()
        self._cache = {} # path -> QPixmap
        self._loading = set() # paths currently loading
        self._max_size = 1024 # Max dimension for thumbnail
        self._workers = {} # path -> (thread, worker)

    def shutdown(self):
        # Stop any running thumbnail threads to avoid "QThread destroyed while running".
        workers = list(self._workers.items())
        for path, (thread, worker) in workers:
            try:
                thread.requestInterruption()
                thread.quit()
                thread.wait(2000)
            except Exception:
                pass
        self._workers.clear()
        self._loading.clear()

    def clear_cache(self):
        """Clear all cached thumbnails to force reload from disk."""
        self._cache.clear()
        self._loading.clear()

    def get_pixmap(self, path: str) -> QPixmap:
        """
        Returns a cached QPixmap if available.
        If not, returns None (or placeholder) and triggers background loading.
        """
        if not path or not os.path.exists(path):
            return None
            
        if path in self._cache:
            return self._cache[path]
            
        if path not in self._loading:
            self._start_loading(path)
            
        return None 

    def _start_loading(self, path):
        self._loading.add(path)
        
        thread = QThread(self)
        worker = ThumbnailWorker(path, self._max_size)
        worker.moveToThread(thread)
        
        thread.started.connect(worker.run)
        worker.finished.connect(self._on_thumbnail_finished)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(lambda p=path: self._on_thread_finished(p))
        
        # Keep reference to avoid GC
        self._workers[path] = (thread, worker)
        
        thread.start()

    def _on_thread_finished(self, path: str):
        if path in self._workers:
            del self._workers[path]

    def _on_thumbnail_finished(self, path, qimage):
        if not qimage.isNull():
            pixmap = QPixmap.fromImage(qimage)
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
