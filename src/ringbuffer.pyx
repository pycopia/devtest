# Fast ring buffer for Python
# cython: language_level=3

from libc cimport stdint
from libc.stddef cimport size_t
from libc.string cimport memcpy, memset
from cpython.mem cimport PyMem_Malloc, PyMem_Free
from cpython.bytes cimport (PyBytes_AsStringAndSize, PyBytes_AS_STRING,
                            PyBytes_FromStringAndSize)


cdef inline size_t _count(size_t head, size_t tail, size_t size):
    return (head - tail) & (size - 1)


cdef inline size_t _count_to_end(size_t head, size_t tail, size_t size):
    cdef size_t end, n
    end = size - tail
    n = (head + end) & (size - 1)
    return n if n < end else end


cdef inline size_t _space(size_t head, size_t tail, size_t size):
    return _count(tail, head + 1, size)


cdef inline size_t _space_to_end(size_t head, size_t tail, size_t size):
    cdef size_t end, n
    end = size - 1 - head
    n = (end + tail) & (size - 1)
    return n if n <= end else end + 1


cdef class RingBuffer:
    cdef size_t _size
    cdef stdint.uint8_t *_buf
    cdef size_t _head
    cdef size_t _tail

    def __cinit__(self, int size=65536):
        if size & (size -1) != 0:
            raise ValueError("Size must be a positive power of 2")
        self._size = <size_t> size
        self._buf = <stdint.uint8_t *> PyMem_Malloc(<size_t> size)
        if self._buf is NULL:
            raise MemoryError("Could not allocate RingBuffer")
        # Zero out memory for security
        memset(<stdint.uint8_t *> self._buf, 0, <size_t> size)
        self._head = 0
        self._tail = 0

    def __dealloc__(self):
        if self._buf is not NULL:
            PyMem_Free(self._buf)

    def clear(self):
        memset(<stdint.uint8_t *> self._buf, 0, self._size)
        self._head = 0
        self._tail = 0

    def read(self, int amt=-1):
        cdef char *bytes_buf
        cdef size_t read_amt, r
        r = _count(self._head, self._tail, self._size)
        if amt < 0 or amt > r:
            amt = r
        if amt <= 0:
            return b""
        buf = PyBytes_FromStringAndSize(NULL, <Py_ssize_t> amt)
        bytes_buf = PyBytes_AS_STRING(buf)
        while amt > 0:
            read_amt = _count_to_end(self._head, self._tail, self._size)
            r = amt if amt <= read_amt else read_amt
            memcpy(bytes_buf, self._buf + self._tail, r)
            self._tail = (self._tail + r) & (self._size - 1)
            bytes_buf += r
            amt -= r
        return buf

    def write(self, bytes data) -> int:
        cdef char *bytes_buf
        cdef Py_ssize_t length
        cdef size_t spc2e
        cdef int written = 0
        PyBytes_AsStringAndSize(data, &bytes_buf, &length)
        while 1:
            spc2e = _space_to_end(self._head, self._tail, self._size)
            if length < spc2e:
                spc2e = length
            if spc2e <= 0:
                break
            memcpy(self._buf + self._head, bytes_buf, spc2e)
            bytes_buf += spc2e
            length -= spc2e
            written += spc2e
            self._head = (self._head + spc2e) & (self._size - 1)
        return <int> written

    def fileno(self):
        return -1

    def close(self):
        return NotImplemented

    def flush(self):
        return NotImplemented

    @property
    def freespace(self):
        return <int> _space(self._head, self._tail, self._size)

    @property
    def size(self):
        return <int> self._size

    @property
    def buffer(self):
        return PyBytes_FromStringAndSize(<char *> self._buf, self._size)

    def __nonzero__(self):
        return self._head == self._tail

    def __len__(self):
        return <int> _count(self._head, self._tail, self._size)

    def __getitem__(self, int index):
        if index >= _count(self._head, self._tail, self._size):
            raise IndexError("index out of range of current buffer size.")
        return <int> self._buf[(self._tail + index) & (self._size - 1)]


