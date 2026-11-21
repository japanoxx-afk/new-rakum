/* Test stand-in for the game's TG_Net.dll (installed as TGNetOrg.dll in the test folder).
 * Imports sendto/recvfrom/bind from WSOCK32.dll like the real one, so rkp2p's IAT hooks apply. */
#define WIN32_LEAN_AND_MEAN
#include <winsock2.h>
#include <windows.h>
#include <stdlib.h>
static SOCKET s = INVALID_SOCKET;
__declspec(dllexport) void *__cdecl TGNet_CreateUDPSocket(void *a, void *port)
{
    WSADATA w; struct sockaddr_in me; u_long nb = 1; char ip[32];
    (void)a;
    WSAStartup(0x0101, &w);
    s = socket(AF_INET, SOCK_DGRAM, 0);
    memset(&me, 0, sizeof me);
    me.sin_family = AF_INET;
    GetEnvironmentVariableA("RK_BIND_IP", ip, sizeof ip);
    me.sin_addr.s_addr = inet_addr(ip);
    me.sin_port = htons((u_short)(size_t)port);
    if (bind(s, (struct sockaddr *)&me, sizeof me) != 0) return NULL;
    ioctlsocket(s, FIONBIO, &nb);
    return &s;
}
__declspec(dllexport) int __cdecl Fake_Send(const char *ip, const char *data, int len)
{
    struct sockaddr_in to; memset(&to, 0, sizeof to);
    to.sin_family = AF_INET; to.sin_addr.s_addr = inet_addr(ip); to.sin_port = htons(11223);
    return sendto(s, data, len, 0, (struct sockaddr *)&to, sizeof to);
}
__declspec(dllexport) int __cdecl Fake_Recv(char *buf, int len, char *from, int *port)
{
    struct sockaddr_in src; int sl = sizeof src;
    int n = recvfrom(s, buf, len, 0, (struct sockaddr *)&src, &sl);
    if (n > 0) { lstrcpyA(from, inet_ntoa(src.sin_addr)); *port = ntohs(src.sin_port); }
    return n;
}
__declspec(dllexport) int __cdecl TGNet_Get_MyIPaddress(char *buf, int size)
{
    lstrcpynA(buf, "26.9.9.9", size);   /* like a PC whose first adapter is Radmin */
    return 1;
}
