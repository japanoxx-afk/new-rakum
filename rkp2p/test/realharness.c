/* Same as harness.c but drives the game's REAL TG_Net.dll (as TGNetOrg.dll) through its own API,
 * the way Rhakmu.exe does: Socket_Init, CreateUDPSocket(hwnd, 11223), WndProc on socket messages,
 * Buffer_Send2UDP and UDPPacket_Peek. Used by test_rkp2p when the game is installed. */
#include <winsock2.h>
#include <windows.h>
#include <stdio.h>
typedef char (__cdecl *init_t)(void);
typedef void *(__cdecl *create_t)(HWND, int);
typedef LRESULT (__cdecl *wndproc_t)(HWND, UINT, WPARAM, LPARAM);
typedef char (__cdecl *bsend_t)(void *, const char *, short, struct sockaddr_in *);
typedef char (__cdecl *peek_t)(void *, void *, char);
static wndproc_t tg_wndproc;
static LRESULT CALLBACK wp(HWND h, UINT m, WPARAM w, LPARAM l)
{
    if (m >= 0x2816 && m <= 0x2817 && tg_wndproc) { tg_wndproc(h, m, w, l); return 0; }
    return DefWindowProcA(h, m, w, l);
}
struct pk { DWORD ip; WORD port; WORD pad; int len; char *data; };
int main(int argc, char **argv)
{
    HMODULE tg; HWND hwnd; WNDCLASSA wc = {0}; void *obj; int i, sent = 0, count, ms;
    init_t init; create_t cr; bsend_t bs; peek_t pk_; struct sockaddr_in to; char buf[2048];
    if (argc < 3) return 2;
    count = atoi(argv[2]); ms = argc > 3 ? atoi(argv[3]) : 6000;
    tg = LoadLibraryA("TG_Net.dll");
    if (!tg) { printf("noload %lu\n", GetLastError()); return 3; }
    init = (init_t)GetProcAddress(tg, "TGNet_Socket_Init");
    cr = (create_t)GetProcAddress(tg, "TGNet_CreateUDPSocket");
    tg_wndproc = (wndproc_t)GetProcAddress(tg, "TGNet_WndProc");
    bs = (bsend_t)GetProcAddress(tg, "TGNet_Buffer_Send2UDP");
    pk_ = (peek_t)GetProcAddress(tg, "TGNet_UDPPacket_Peek");
    wc.lpfnWndProc = wp; wc.lpszClassName = "rkh"; wc.hInstance = GetModuleHandleA(NULL);
    RegisterClassA(&wc);
    hwnd = CreateWindowA("rkh", "rkh", 0, 0, 0, 10, 10, NULL, NULL, wc.hInstance, NULL);
    init();
    obj = cr(hwnd, 11223);
    if (!obj) { printf("nobind\n"); return 4; }
    memset(&to, 0, sizeof to); to.sin_family = AF_INET; to.sin_addr.s_addr = inet_addr(argv[1]); to.sin_port = htons(11223);
    printf("ready\n"); fflush(stdout);
    for (i = 0; i < ms / 20; i++) {
        MSG msg; struct pk p;
        if (sent < count && i >= 50 && i % 10 == 5) {
            char m[32]; int k = sprintf(m, "msg %d", sent++);
            bs(obj, m, (short)k, &to);
        }
        while (PeekMessageA(&msg, NULL, 0, 0, PM_REMOVE)) { TranslateMessage(&msg); DispatchMessageA(&msg); }
        for (;;) {
            memset(&p, 0, sizeof p); p.data = buf;
            if (!pk_(obj, &p, 1)) break;
            if (p.len >= 0 && p.len < (int)sizeof buf) buf[p.len] = 0;
            { struct in_addr a; a.s_addr = p.ip; printf("recv %s:%u %s\n", inet_ntoa(a), ntohs(p.port), buf); fflush(stdout); }
        }
        Sleep(20);
    }
    return 0;
}
