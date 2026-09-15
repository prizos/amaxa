/*
 * Minimal newlib system calls: stdout/stderr go to the console UART with
 * LF -> CRLF translation; everything else is a stub.
 */

#include <errno.h>
#include <stddef.h>
#include <sys/stat.h>

#include "hw.h"

/* Symbols from the linker script. */
extern char end;
extern char _estack;
extern char _Min_Stack_Size;

int _write(int fd, char *ptr, int len)
{
    (void)fd;
    static const char cr = '\r';
    int start = 0;
    for (int i = 0; i < len; i++) {
        if (ptr[i] == '\n') {
            hw_console_write(&ptr[start], (size_t)(i - start));
            hw_console_write(&cr, 1U);
            start = i;
        }
    }
    hw_console_write(&ptr[start], (size_t)(len - start));
    return len;
}

int _read(int fd, char *ptr, int len)
{
    (void)fd;
    (void)ptr;
    (void)len;
    errno = ENOSYS;
    return -1;
}

void *_sbrk(ptrdiff_t increment)
{
    static char *heap_end;
    char *stack_floor = &_estack - (size_t)&_Min_Stack_Size;
    if (heap_end == NULL) {
        heap_end = &end;
    }
    if (heap_end + increment > stack_floor) {
        errno = ENOMEM;
        return (void *)-1;
    }
    char *previous = heap_end;
    heap_end += increment;
    return previous;
}

int _close(int fd)
{
    (void)fd;
    return -1;
}

int _fstat(int fd, struct stat *st)
{
    (void)fd;
    st->st_mode = S_IFCHR;
    return 0;
}

int _isatty(int fd)
{
    (void)fd;
    return 1;
}

int _lseek(int fd, int offset, int whence)
{
    (void)fd;
    (void)offset;
    (void)whence;
    return 0;
}

int _getpid(void)
{
    return 1;
}

int _kill(int pid, int sig)
{
    (void)pid;
    (void)sig;
    errno = EINVAL;
    return -1;
}

void _exit(int status)
{
    (void)status;
    hw_panic("exit");
}
