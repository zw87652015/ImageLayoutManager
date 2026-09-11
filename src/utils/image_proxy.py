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


# Display names for the file extensions the app imports. Keyed by the
# extension so ".jpg"/".jpeg" and ".tif"/".tiff" report one canonical name.
_FORMAT_NAMES = {
    '.svg': 'SVG', '.pdf': 'PDF', '.eps': 'EPS',
    '.png': 'PNG', '.jpg': 'JPEG', '.jpeg': 'JPEG',
    '.tif': 'TIFF', '.tiff': 'TIFF', '.bmp': 'BMP',
    '.gif': 'GIF', '.webp': 'WebP',
}


def image_format_name(path: str) -> str:
    """Short uppercase format name for *path* ("SVG", "TIFF", ...).

    Falls back to the bare extension so an unsupported or unknown file is
    still described honestly instead of being mislabelled as a known format.
    """
    if not path:
        return ""
    ext = os.path.splitext(path)[1].lower()
    return _FORMAT_NAMES.get(ext) or ext.lstrip('.').upper()


def _natural_key(path: str):
    import re
    return [int(tok) if tok.isdigit() else tok.lower()
            for tok in re.split(r'(\d+)', os.path.basename(path))]


def collect_importable_images(paths, recursive: bool = True) -> list:
    """Expand files/folders dropped by the user into a de-duplicated,
    naturally sorted list of supported image paths (``fig1`` < ``fig2`` <
    ``fig10``). Folders are walked in sorted order; hidden entries are skipped.
    Project files and anything else unsupported are ignored."""
    seen = set()
    result = []

    def _add(p):
        p = os.path.normpath(p)
        key = os.path.normcase(os.path.abspath(p))
        if key not in seen and is_supported_image(p) and os.path.isfile(p):
            seen.add(key)
            result.append(p)

    for path in paths:
        if os.path.isdir(path):
            for root, dirs, files in os.walk(path):
                dirs[:] = sorted(d for d in dirs if not d.startswith('.')) if recursive else []
                for name in sorted(files, key=_natural_key):
                    if not name.startswith('.'):
                        _add(os.path.join(root, name))
        elif path:
            _add(path)
    # Explorer hands over multi-selections in arbitrary order, so sort the
    # final list naturally to get a predictable panel sequence.
    result.sort(key=_natural_key)
    return result

class ThumbnailWorker(QRunnable):
    def __init__(self, path, max_size, callback, svg_override_bytes=None, raster_override=None):
        super().__init__()
        self.path = path
        self.max_size = max_size
        self.callback = callback
        self.svg_override_bytes = svg_override_bytes
        self.raster_override = raster_override
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
        from PyQt6.QtCore import QByteArray
        from src.utils.svg_utils import sanitize_svg_bytes
        if self.svg_override_bytes is not None:
            svg_bytes = sanitize_svg_bytes(self.svg_override_bytes)
        else:
            with open(self.path, "rb") as _f:
                svg_bytes = sanitize_svg_bytes(_f.read())
        renderer = QSvgRenderer(QByteArray(svg_bytes))
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
        if self.raster_override:
            from src.utils.raster_text_utils import load_raster_with_overrides
            img = load_raster_with_overrides(self.path, self.raster_override)
        else:
            with Image.open(self.path) as src:
                img = src.convert('RGBA')
        img.thumbnail((self.max_size, self.max_size), Image.Resampling.LANCZOS)
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
    _thumbnail_finished = pyqtSignal(str, QImage, object, object)

    def __init__(self, max_cache_items=256):
        super().__init__()
        self._cache = OrderedDict() # path -> QPixmap, LRU ordered
        self._max_cache_items = max_cache_items
        self._loading = set() # paths currently loading
        self._max_size = 1024 # Max dimension for thumbnail
        self._thread_pool = QThreadPool.globalInstance()
        self._thread_pool.setMaxThreadCount(4)  # Limit concurrent image loads
        self._svg_overrides = {}  # path -> bytes (pre-computed modified SVG)
        # Per-path subscriber callbacks: path -> list[callable]
        # Each callable is invoked (instead of the broadcast signal) when that path loads.
        self._subscribers: dict[object, list] = {}
        self._request_tokens = {}
        self._thumbnail_finished.connect(
            self._on_thumbnail_finished, Qt.ConnectionType.QueuedConnection
        )

    def shutdown(self):
        # Wait for all workers to finish
        self._thread_pool.waitForDone(2000)
        self._loading.clear()
        self._request_tokens.clear()

    def clear_cache(self):
        """Clear all cached thumbnails to force reload from disk."""
        self._cache.clear()
        self._loading.clear()
        self._request_tokens.clear()

    def invalidate(self, path: str):
        """Drop a single cached entry so the next get_pixmap reloads from disk."""
        if not path:
            return
        keys = set(self._cache) | self._loading | set(self._request_tokens)
        for key in keys:
            if key == path or isinstance(key, tuple) and key[0] == path:
                self._cache.pop(key, None)
                self._loading.discard(key)
                self._request_tokens.pop(key, None)

    def subscribe(self, path: str, callback) -> None:
        """Register *callback* to be called when *path* finishes loading.
        Only that one callback fires — no broadcast to unrelated cells."""
        if path not in self._subscribers:
            self._subscribers[path] = []
        if callback not in self._subscribers[path]:
            self._subscribers[path].append(callback)

    def unsubscribe(self, path: str, callback) -> None:
        """Remove a previously registered callback."""
        for key in list(self._subscribers):
            if key == path or isinstance(key, tuple) and key[0] == path:
                try:
                    self._subscribers[key].remove(callback)
                except ValueError:
                    pass
                if not self._subscribers[key]:
                    del self._subscribers[key]

    def set_svg_override(self, path: str, content: bytes):
        """Set pre-computed modified SVG bytes for a path and invalidate its cache entry."""
        self._svg_overrides[path] = content
        self.invalidate(path)

    def clear_svg_overrides(self):
        """Remove all SVG overrides and invalidate their cache entries."""
        for path in self._svg_overrides:
            self.invalidate(path)
        self._svg_overrides.clear()

    def get_pixmap(self, path: str, callback=None, svg_override_bytes=None,
                   raster_override=None) -> QPixmap:
        """
        Returns a cached QPixmap if available.
        If not, returns None and triggers background loading.
        When *callback* is provided it is registered as a subscriber so only
        that callback fires when the load completes (instead of a global broadcast).
        Uses LRU eviction when cache is full.
        """
        if not path or not os.path.exists(path):
            return None

        key = path
        if svg_override_bytes is not None:
            svg_override_bytes = bytes(svg_override_bytes)
            key = (path, hashlib.sha256(svg_override_bytes).hexdigest())
        elif raster_override:
            from src.utils.raster_text_utils import spec_key
            key = (path, hashlib.sha256(spec_key(raster_override).encode()).hexdigest())
        else:
            svg_override_bytes = self._svg_overrides.get(path)

        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key]

        if callback is not None:
            self.subscribe(key, callback)

        if key not in self._loading:
            self._start_loading(path, key, svg_override_bytes, raster_override)

        return None

    def _start_loading(self, path, key, svg_override_bytes, raster_override=None):
        self._loading.add(key)
        token = object()
        self._request_tokens[key] = token
        worker = ThumbnailWorker(
            path, self._max_size,
            lambda original_path, qimage: self._thumbnail_finished.emit(
                original_path, qimage, key, token
            ),
            svg_override_bytes,
            raster_override,
        )
        self._thread_pool.start(worker)

    def _on_thumbnail_finished(self, path, qimage, key, token):
        if self._request_tokens.get(key) is not token:
            return
        self._request_tokens.pop(key)
        self._loading.discard(key)

        if not qimage.isNull() and self._max_cache_items > 0:
            pixmap = QPixmap.fromImage(qimage)

            # Evict oldest item if cache is full (LRU)
            while len(self._cache) >= self._max_cache_items:
                self._cache.popitem(last=False)

            self._cache[key] = pixmap

        # Notify only subscribers for this specific path (avoids O(N) broadcast)
        callbacks = self._subscribers.pop(key, [])
        if callbacks:
            for cb in callbacks:
                try:
                    cb(path)
                except Exception:
                    pass
        else:
            # Fallback: broadcast via signal for any legacy listeners
            self.thumbnail_ready.emit(path)

# Global instance
_instance = None

def get_image_proxy():
    global _instance
    if _instance is None:
        _instance = ImageProxy()
    return _instance
