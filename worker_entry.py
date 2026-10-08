"""Windowless packaged worker entry; Qt supplies inherited pipe handles."""
import os
import sys


def connect_standard_pipes():
    if os.name != 'nt':
        return
    import ctypes
    import msvcrt
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.GetStdHandle.argtypes = [ctypes.c_uint32]
    kernel.GetStdHandle.restype = ctypes.c_void_p
    for name, number, mode, flags in (
        ('stdin', -10, 'r', os.O_RDONLY),
        ('stdout', -11, 'w', os.O_WRONLY),
        ('stderr', -12, 'w', os.O_WRONLY),
    ):
        if getattr(sys, name) is not None:
            continue
        handle = kernel.GetStdHandle(number & 0xffffffff)
        if handle in (None, ctypes.c_void_p(-1).value):
            raise RuntimeError('The PDF worker must be launched by Light PDF Editor with redirected pipes.')
        descriptor = msvcrt.open_osfhandle(handle, flags | os.O_BINARY)
        setattr(sys, name, os.fdopen(descriptor, mode, encoding='utf-8', buffering=1))


if __name__ == '__main__':
    try:
        connect_standard_pipes()
    except RuntimeError:
        sys.exit(2)
    if '--ocr' in sys.argv:
        from ocr_core import main
    else:
        from pdf_worker import main
    main()
