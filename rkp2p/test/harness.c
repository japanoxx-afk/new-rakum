/* rkp2p test "game": loads TG_Net.dll (proxy) from its own folder, creates the 11223 socket,
 * sends "msg N" to the peer and prints every packet it receives with its (rewritten) source. */
#include <windows.h>
#include <stdio.h>
typedef void *(__cdecl *create_t)(void *, void *);
typedef int (__cdecl *send_t)(const char *, const char *, int);
typedef int (__cdecl *recv_t)(char *, int, char *, int *);
typedef int (__cdecl *myip_t)(char *, int);
int main(int argc, char **argv)
{
    HMODULE tg, org; create_t cr; send_t sd; recv_t rv; int i, sent = 0, count, ms;
    char buf[2048], from[32];
    if (argc < 4) return 2;
    SetEnvironmentVariableA("RK_BIND_IP", argv[1]);
    count = atoi(argv[3]); ms = argc > 4 ? atoi(argv[4]) : 6000;
    tg = LoadLibraryA("TG_Net.dll");
    if (!tg) { printf("noload %lu\n", GetLastError()); return 3; }
    cr = (create_t)GetProcAddress(tg, "TGNet_CreateUDPSocket");
    if (!cr(NULL, (void *)11223)) { printf("nobind\n"); return 4; }
    org = GetModuleHandleA("TGNetOrg.dll");
    sd = (send_t)GetProcAddress(org, "Fake_Send");
    rv = (recv_t)GetProcAddress(org, "Fake_Recv");
    printf("ready\n"); fflush(stdout);
    for (i = 0; i < ms / 20; i++) {
        int port, n;
        if (i == 40) {   /* the game asks when it creates a room, well after the socket is bound */
            myip_t mi = (myip_t)GetProcAddress(tg, "TGNet_Get_MyIPaddress");
            char ip[128] = "";
            printf("myip %s\n", mi && mi(ip, sizeof ip) ? ip : "-"); fflush(stdout);
        }
        if (sent < count && i >= 50 && i % 10 == 5) {
            char m[32]; int k = sprintf(m, "msg %d", sent++);
            sd(argv[2], m, k);
        }
        while ((n = rv(buf, sizeof buf, from, &port)) > 0) {
            buf[n] = 0;
            printf("recv %s:%d %s\n", from, port, buf); fflush(stdout);
        }
        Sleep(20);
    }
    return 0;
}
