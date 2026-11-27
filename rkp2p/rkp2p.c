/*
 * rkp2p: NAT hole punching for RhakMu (TG_Net.dll proxy).
 *
 * Installed as TG_Net.dll; the original is renamed to TGNetOrg.dll and every export
 * except TGNet_CreateUDPSocket is forwarded to it (tg_net.def). Before the game creates
 * its UDP 11223 socket we patch TGNetOrg's imports of sendto/recvfrom/bind so the game
 * logic stays untouched:
 *
 *   game -> sendto(peerIP:11223)  : routed to the peer's real NAT endpoint (hole punched)
 *                                   or wrapped through the lobby server's UDP relay.
 *   recvfrom -> game              : the source is rewritten back to peerIP:11223, so the
 *                                   game's "which player sent this" check still matches.
 *
 * Peers the server does not know (old launchers, Radmin/LAN addresses) are sent to
 * directly exactly as before ("pass").
 *
 * Control packets start with "RKP2" + type. The server side lives in server.py
 * (P2PRendezvous, on the same UDP socket as the DP8 relay).
 */
#define WIN32_LEAN_AND_MEAN
#include <winsock2.h>
#include <windows.h>
#include <stdio.h>
#include <string.h>
#include <stdarg.h>

#define GAME_PORT 11223
#define MAXPEER 16
#define MAXQ 32
#define MAXPKT 1024
#define HDR 5

enum { T_HELLO = 0x01, T_QUERY = 0x02, T_RELAY = 0x10, T_DELIVER = 0x11,
       T_PUNCH = 0x20, T_PUNCH_ACK = 0x21,
       T_HELLO_ACK = 0x81, T_ENDPOINT = 0x82, T_PUNCH_REQ = 0x83, T_UNKNOWN = 0x84 };
enum { S_NONE, S_QUERY, S_PUNCH, S_DIRECT, S_RELAY, S_PASS };
static const char *SNAME[] = { "none", "query", "punch", "direct", "relay", "pass" };

#define QUERY_RETRY_MS 700
#define QUERY_GIVEUP_MS 3000
#define PUNCH_EVERY_MS 100
#define PUNCH_GIVEUP_MS 2500
#define HELLO_EVERY_MS 10000
#define HELLO_FAST_MS 1000
#define KEEPALIVE_MS 5000
#define STALE_MS 8000
#define FORGET_MS 60000
#define DIRECT_SILENT_MS 1500   /* direct link: relayed packets arrive but nothing direct for this long */

typedef int (WINAPI *sendto_t)(SOCKET, const char *, int, int, const struct sockaddr *, int);
typedef int (WINAPI *recvfrom_t)(SOCKET, char *, int, int, struct sockaddr *, int *);
typedef int (WINAPI *bind_t)(SOCKET, const struct sockaddr *, int);

static sendto_t real_sendto;
static recvfrom_t real_recvfrom;
static bind_t real_bind;

typedef struct { int len; char data[MAXPKT]; } pkt_t;
typedef struct {
    int used;
    u_long ip;                 /* address the game uses for this player (network order) */
    int state;
    struct sockaddr_in ep;     /* real endpoint (hole punched) */
    DWORD t_state, t_ctl, t_rx, t_tx;
    DWORD t_drx;               /* last packet heard straight from the peer (not through the server) */
    int nq;
    pkt_t q[MAXQ];
} peer_t;

static CRITICAL_SECTION g_cs;
static volatile SOCKET g_sock = INVALID_SOCKET;
static int g_enabled;
static int g_log = 1;
static int g_allow_loopback;   /* test only: peers on 127.x (rkp2p.ini allow_loopback=1) */
static int g_block_peers;      /* test only: drop packets from peers, as a closed NAT would */
static struct sockaddr_in g_srv;
static int g_hello_ok;
static u_long g_pub_ip;        /* our address as the server sees it (HELLO_ACK) */
static DWORD g_t_hello;
static peer_t g_peer[MAXPEER];
static char g_dir[MAX_PATH];
static HANDLE g_thread;
static int g_hooked;
static u_long g_token;

/* ---------- logging ---------- */
static void logf_(const char *fmt, ...)
{
    char path[MAX_PATH + 16], line[512];
    SYSTEMTIME st;
    va_list ap;
    FILE *f;
    if (!g_log)
        return;
    GetLocalTime(&st);
    va_start(ap, fmt);
    _vsnprintf(line, sizeof line - 1, fmt, ap);
    va_end(ap);
    line[sizeof line - 1] = 0;
    _snprintf(path, sizeof path, "%srkp2p.log", g_dir);
    f = fopen(path, "a");
    if (!f)
        return;
    fprintf(f, "%02d:%02d:%02d.%03d %s\n", st.wHour, st.wMinute, st.wSecond, st.wMilliseconds, line);
    fclose(f);
}

static const char *ipstr(u_long ip, char *buf)
{
    unsigned char *b = (unsigned char *)&ip;
    sprintf(buf, "%u.%u.%u.%u", b[0], b[1], b[2], b[3]);
    return buf;
}

/* ---------- config ---------- */
static void load_config(HMODULE self)
{
    char ini[MAX_PATH + 16], server[128], *colon, *slash;
    GetModuleFileNameA(self, g_dir, MAX_PATH);
    slash = strrchr(g_dir, '\\');
    if (slash)
        slash[1] = 0;
    _snprintf(ini, sizeof ini, "%srkp2p.ini", g_dir);
    g_enabled = GetPrivateProfileIntA("rkp2p", "enabled", 0, ini);
    g_log = GetPrivateProfileIntA("rkp2p", "log", 1, ini);
    g_allow_loopback = GetPrivateProfileIntA("rkp2p", "allow_loopback", 0, ini);
    g_block_peers = GetPrivateProfileIntA("rkp2p", "test_block_peers", 0, ini);
    GetPrivateProfileStringA("rkp2p", "server", "", server, sizeof server, ini);
    memset(&g_srv, 0, sizeof g_srv);
    colon = strchr(server, ':');
    if (colon) {
        *colon = 0;
        g_srv.sin_family = AF_INET;
        g_srv.sin_addr.s_addr = inet_addr(server);
        g_srv.sin_port = htons((u_short)atoi(colon + 1));
    }
    if (g_srv.sin_family != AF_INET || g_srv.sin_addr.s_addr == INADDR_NONE || !g_srv.sin_port)
        g_enabled = 0;
    if (g_log) {   /* keep the log small: start over above 512 KB */
        char path[MAX_PATH + 16];
        WIN32_FILE_ATTRIBUTE_DATA a;
        _snprintf(path, sizeof path, "%srkp2p.log", g_dir);
        if (GetFileAttributesExA(path, GetFileExInfoStandard, &a) && a.nFileSizeLow > 512 * 1024)
            DeleteFileA(path);
    }
}

/* ---------- packets ---------- */
static int ctl(char *buf, int type)
{
    memcpy(buf, "RKP2", 4);
    buf[4] = (char)type;
    return HDR;
}

static void send_srv(const char *buf, int len)
{
    real_sendto(g_sock, buf, len, 0, (const struct sockaddr *)&g_srv, sizeof g_srv);
}

static void send_hello(void)
{
    char b[8];
    int n = ctl(b, T_HELLO);
    b[n++] = 1;   /* protocol version */
    send_srv(b, n);
    g_t_hello = GetTickCount();
}

static void send_query(peer_t *p)
{
    char b[16];
    int n = ctl(b, T_QUERY);
    memcpy(b + n, &p->ip, 4);
    send_srv(b, n + 4);
    p->t_ctl = GetTickCount();
}

static void send_punch(peer_t *p, int type)
{
    char b[16];
    int n = ctl(b, type);
    memcpy(b + n, &g_token, 4);
    real_sendto(g_sock, b, n + 4, 0, (const struct sockaddr *)&p->ep, sizeof p->ep);
    p->t_ctl = GetTickCount();
}

static void send_game(peer_t *p, const char *data, int len)
{
    struct sockaddr_in to;
    p->t_tx = GetTickCount();
    if (p->state == S_DIRECT) {
        real_sendto(g_sock, data, len, 0, (const struct sockaddr *)&p->ep, sizeof p->ep);
    } else if (p->state == S_RELAY) {
        char b[HDR + 4 + MAXPKT];
        int n = ctl(b, T_RELAY);
        memcpy(b + n, &p->ip, 4);
        memcpy(b + n + 4, data, len);
        send_srv(b, n + 4 + len);
    } else {
        memset(&to, 0, sizeof to);
        to.sin_family = AF_INET;
        to.sin_addr.s_addr = p->ip;
        to.sin_port = htons(GAME_PORT);
        real_sendto(g_sock, data, len, 0, (const struct sockaddr *)&to, sizeof to);
    }
}

static void set_state(peer_t *p, int st)
{
    char a[20], e[20];
    int i;
    if (p->state != st)
        logf_("peer %s: %s -> %s (endpoint %s:%u, %d queued)", ipstr(p->ip, a), SNAME[p->state], SNAME[st],
              ipstr(p->ep.sin_addr.s_addr, e), ntohs(p->ep.sin_port), p->nq);
    p->state = st;
    p->t_state = GetTickCount();
    if (st == S_DIRECT || st == S_RELAY || st == S_PASS) {
        for (i = 0; i < p->nq; i++)
            send_game(p, p->q[i].data, p->q[i].len);
        p->nq = 0;
    }
}

static peer_t *find_ip(u_long ip)
{
    int i;
    for (i = 0; i < MAXPEER; i++)
        if (g_peer[i].used && g_peer[i].ip == ip)
            return &g_peer[i];
    return NULL;
}

static peer_t *find_or_add(u_long ip)
{
    peer_t *p = find_ip(ip);
    int i, old = 0;
    if (p)
        return p;
    for (i = 0; i < MAXPEER; i++) {
        if (!g_peer[i].used)
            break;
        if (g_peer[i].t_tx < g_peer[old].t_tx)
            old = i;
    }
    p = &g_peer[i < MAXPEER ? i : old];
    memset(p, 0, sizeof *p);
    p->used = 1;
    p->ip = ip;
    p->state = S_NONE;
    p->t_rx = p->t_tx = p->t_state = p->t_drx = GetTickCount();
    return p;
}

/* Peer a packet from `src` belongs to: exact endpoint, else same address while punching/direct
 * (a symmetric NAT on the other side shows up with a different port). */
static peer_t *find_src(const struct sockaddr_in *src)
{
    int i;
    for (i = 0; i < MAXPEER; i++) {
        peer_t *p = &g_peer[i];
        if (p->used && (p->state == S_PUNCH || p->state == S_DIRECT || p->state == S_RELAY)
            && p->ep.sin_addr.s_addr == src->sin_addr.s_addr && p->ep.sin_port == src->sin_port)
            return p;
    }
    for (i = 0; i < MAXPEER; i++) {
        peer_t *p = &g_peer[i];
        if (p->used && (p->state == S_PUNCH || p->state == S_DIRECT)
            && p->ep.sin_addr.s_addr == src->sin_addr.s_addr)
            return p;
    }
    return NULL;
}

static int wanted(SOCKET s, const struct sockaddr *to, int len)
{
    const struct sockaddr_in *a = (const struct sockaddr_in *)to;
    u_long ip;
    if (!g_enabled || s != g_sock || !to || len > MAXPKT || a->sin_family != AF_INET
        || ntohs(a->sin_port) != GAME_PORT)
        return 0;
    ip = ntohl(a->sin_addr.s_addr);
    if (ip == 0 || ip == 0xFFFFFFFF || ((ip >> 24) == 127 && !g_allow_loopback) || (ip & 0xFF) == 0xFF)
        return 0;
    return 1;
}

/* ---------- hooks ---------- */
static int WINAPI h_sendto(SOCKET s, const char *buf, int len, int flags, const struct sockaddr *to, int tolen)
{
    peer_t *p;
    if (!wanted(s, to, len))
        return real_sendto(s, buf, len, flags, to, tolen);
    EnterCriticalSection(&g_cs);
    p = find_or_add(((const struct sockaddr_in *)to)->sin_addr.s_addr);
    if (p->state == S_NONE) {
        if (g_hello_ok) {
            p->state = S_QUERY;
            p->t_state = GetTickCount();
            send_query(p);
        } else {
            set_state(p, S_PASS);   /* server without hole punching: behave as before */
        }
    }
    if (p->state == S_QUERY || p->state == S_PUNCH) {
        if (p->nq < MAXQ) {
            memcpy(p->q[p->nq].data, buf, len);
            p->q[p->nq++].len = len;
            p->t_tx = GetTickCount();
        } else {
            int keep = p->state;
            p->state = S_PASS;
            send_game(p, buf, len);
            p->state = keep;
        }
    } else {
        send_game(p, buf, len);
    }
    LeaveCriticalSection(&g_cs);
    return len;
}

static void got_endpoint(peer_t *p, const char *d)
{
    memset(&p->ep, 0, sizeof p->ep);
    p->ep.sin_family = AF_INET;
    memcpy(&p->ep.sin_addr.s_addr, d, 4);
    memcpy(&p->ep.sin_port, d + 4, 2);
}

/* Handle a control packet. Returns the length of a game payload left at out[0..] (relay
 * delivery, with *src set to the sender's game address) or -1 when it was consumed. */
static int handle_ctl(const char *b, int n, struct sockaddr_in *src, char *out, int outlen)
{
    int type = (unsigned char)b[4];
    const char *d = b + HDR;
    int dl = n - HDR;
    int from_srv = src->sin_addr.s_addr == g_srv.sin_addr.s_addr && src->sin_port == g_srv.sin_port;
    char a[20], e[20];
    peer_t *p;
    u_long ip;

    if (type == T_PUNCH || type == T_PUNCH_ACK) {
        if (type == T_PUNCH) {
            char r[16];
            int k = ctl(r, T_PUNCH_ACK);
            memcpy(r + k, &g_token, 4);
            real_sendto(g_sock, r, k + 4, 0, (const struct sockaddr *)src, sizeof *src);
        }
        p = find_src(src);
        if (p) {
            p->t_rx = p->t_drx = GetTickCount();
            if (p->state == S_PUNCH || p->state == S_RELAY) {
                p->ep = *src;
                set_state(p, S_DIRECT);
            } else if (p->state == S_DIRECT && p->ep.sin_port != src->sin_port) {
                /* the peer came back from another port (new socket / new NAT mapping): follow it */
                logf_("peer %s: direct endpoint port %u -> %u", ipstr(p->ip, a), ntohs(p->ep.sin_port),
                      ntohs(src->sin_port));
                p->ep = *src;
            }
        }
        return -1;
    }
    if (!from_srv)
        return -1;
    switch (type) {
    case T_HELLO_ACK:
        if (dl >= 6 && !g_hello_ok) {
            memcpy(&ip, d, 4);
            logf_("server %s:%u sees us as %s:%u", ipstr(g_srv.sin_addr.s_addr, a), ntohs(g_srv.sin_port),
                  ipstr(ip, e), ntohs(*(u_short *)(d + 4)));
        }
        if (dl >= 6)
            memcpy(&g_pub_ip, d, 4);
        g_hello_ok = 1;
        break;
    case T_ENDPOINT:
        if (dl >= 10) {
            memcpy(&ip, d, 4);
            p = find_ip(ip);
            if (p && p->state == S_QUERY) {
                got_endpoint(p, d + 4);
                set_state(p, S_PUNCH);
                send_punch(p, T_PUNCH);
            }
        }
        break;
    case T_PUNCH_REQ:
        if (dl >= 10) {
            memcpy(&ip, d, 4);
            p = find_or_add(ip);
            /* The peer asked the server for us, so it starts from nothing (it restarted the game,
             * or its NAT gave it another port). A direct link we still remember points at its old
             * endpoint: unless it is exactly the same one, punch again towards the new endpoint. */
            if (p->state != S_DIRECT || memcmp(&p->ep.sin_addr.s_addr, d + 4, 4) != 0
                || memcmp(&p->ep.sin_port, d + 8, 2) != 0) {
                got_endpoint(p, d + 4);
                set_state(p, S_PUNCH);
                send_punch(p, T_PUNCH);
            }
        }
        break;
    case T_UNKNOWN:
        if (dl >= 4) {
            memcpy(&ip, d, 4);
            p = find_ip(ip);
            if (p && p->state == S_QUERY)
                set_state(p, S_PASS);
        }
        break;
    case T_DELIVER:
        if (dl > 4) {
            int len = dl - 4;
            memcpy(&ip, d, 4);
            if (len > outlen)
                len = outlen;
            memmove(out, d + 4, len);
            memset(src, 0, sizeof *src);
            src->sin_family = AF_INET;
            src->sin_addr.s_addr = ip;
            src->sin_port = htons(GAME_PORT);
            /* A relayed packet means the peer cannot reach us directly. Answer the same way when we
             * have no working direct link of our own: unknown peer, plain sending, or a "direct"
             * link on which nothing has arrived for a while (stale endpoint). */
            p = find_or_add(ip);
            p->t_rx = GetTickCount();
            if (p->state == S_NONE || p->state == S_PASS
                || (p->state == S_DIRECT && p->t_rx - p->t_drx > DIRECT_SILENT_MS))
                set_state(p, S_RELAY);
            return len;
        }
        break;
    }
    return -1;
}

static int WINAPI h_recvfrom(SOCKET s, char *buf, int len, int flags, struct sockaddr *from, int *fromlen)
{
    char tmp[HDR + 4 + MAXPKT + 64];
    if (!g_enabled || s != g_sock)
        return real_recvfrom(s, buf, len, flags, from, fromlen);
    for (;;) {
        struct sockaddr_in src;
        int sl = sizeof src, n;
        n = real_recvfrom(s, tmp, sizeof tmp, flags, (struct sockaddr *)&src, &sl);
        if (n < 0)
            return n;
        if (g_block_peers && !(src.sin_addr.s_addr == g_srv.sin_addr.s_addr && src.sin_port == g_srv.sin_port))
            continue;
        EnterCriticalSection(&g_cs);
        if (n >= HDR && memcmp(tmp, "RKP2", 4) == 0) {
            int r = handle_ctl(tmp, n, &src, tmp, sizeof tmp);
            LeaveCriticalSection(&g_cs);
            if (r < 0) {
                u_long pending = 0;
                if (ioctlsocket(s, FIONREAD, &pending) != 0 || pending == 0) {
                    WSASetLastError(WSAEWOULDBLOCK);
                    return SOCKET_ERROR;
                }
                continue;
            }
            n = r;
        } else {
            peer_t *p = find_src(&src);
            if (p) {
                p->t_rx = p->t_drx = GetTickCount();
                if (p->state == S_PUNCH)
                    set_state(p, S_DIRECT);
                src.sin_addr.s_addr = p->ip;
                src.sin_port = htons(GAME_PORT);
            }
            LeaveCriticalSection(&g_cs);
        }
        if (n > len)
            n = len;
        memcpy(buf, tmp, n);
        if (from && fromlen) {
            int c = *fromlen < (int)sizeof src ? *fromlen : (int)sizeof src;
            memcpy(from, &src, c);
            *fromlen = c;
        }
        return n;
    }
}

static DWORD WINAPI worker(LPVOID arg)
{
    (void)arg;
    for (;;) {
        DWORD now;
        int i;
        Sleep(30);
        if (g_sock == INVALID_SOCKET)
            continue;
        EnterCriticalSection(&g_cs);
        now = GetTickCount();
        if (now - g_t_hello >= (DWORD)(g_hello_ok ? HELLO_EVERY_MS : HELLO_FAST_MS))
            send_hello();
        for (i = 0; i < MAXPEER; i++) {
            peer_t *p = &g_peer[i];
            if (!p->used)
                continue;
            switch (p->state) {
            case S_QUERY:
                if (now - p->t_state >= QUERY_GIVEUP_MS)
                    set_state(p, S_PASS);
                else if (now - p->t_ctl >= QUERY_RETRY_MS)
                    send_query(p);
                break;
            case S_PUNCH:
                if (now - p->t_state >= PUNCH_GIVEUP_MS)
                    set_state(p, S_RELAY);
                else if (now - p->t_ctl >= PUNCH_EVERY_MS)
                    send_punch(p, T_PUNCH);
                break;
            case S_DIRECT:
                /* we keep sending but hear nothing: the path broke, ask the server again */
                if ((int)(p->t_tx - p->t_rx) > STALE_MS && now - p->t_state > STALE_MS) {
                    set_state(p, S_NONE);
                } else if (now - p->t_ctl >= KEEPALIVE_MS && now - p->t_rx < FORGET_MS) {
                    send_punch(p, T_PUNCH);
                }
                break;
            default:
                break;
            }
            if (p->state != S_QUERY && p->state != S_PUNCH && now - p->t_rx > FORGET_MS
                && now - p->t_tx > FORGET_MS)
                p->used = 0;
        }
        LeaveCriticalSection(&g_cs);
    }
    return 0;
}

static int WINAPI h_bind(SOCKET s, const struct sockaddr *addr, int len)
{
    int r = real_bind(s, addr, len);
    const struct sockaddr_in *a = (const struct sockaddr_in *)addr;
    int type = 0, tl = sizeof type;
    if (r == 0 && addr && a->sin_family == AF_INET && ntohs(a->sin_port) == GAME_PORT
        && getsockopt(s, SOL_SOCKET, SO_TYPE, (char *)&type, &tl) == 0 && type == SOCK_DGRAM) {
        EnterCriticalSection(&g_cs);
        g_sock = s;
        g_hello_ok = 0;
        memset(g_peer, 0, sizeof g_peer);
        if (g_enabled) {
            char b[20];
            logf_("game UDP socket bound; hole punching via %s:%u", ipstr(g_srv.sin_addr.s_addr, b),
                  ntohs(g_srv.sin_port));
            send_hello();
            if (!g_thread)
                g_thread = CreateThread(NULL, 0, worker, NULL, 0, NULL);
        }
        LeaveCriticalSection(&g_cs);
    }
    return r;
}

/* ---------- IAT patch on TGNetOrg.dll ---------- */
static int patch_iat(HMODULE mod)
{
    BYTE *base = (BYTE *)mod;
    IMAGE_DOS_HEADER *dos = (IMAGE_DOS_HEADER *)base;
    IMAGE_NT_HEADERS *nt = (IMAGE_NT_HEADERS *)(base + dos->e_lfanew);
    IMAGE_DATA_DIRECTORY *dir = &nt->OptionalHeader.DataDirectory[IMAGE_DIRECTORY_ENTRY_IMPORT];
    IMAGE_IMPORT_DESCRIPTOR *imp = (IMAGE_IMPORT_DESCRIPTOR *)(base + dir->VirtualAddress);
    int done = 0;
    for (; imp->Name; imp++) {
        const char *name = (const char *)(base + imp->Name);
        IMAGE_THUNK_DATA *oft, *ft;
        if (_stricmp(name, "WSOCK32.dll") != 0 && _stricmp(name, "WS2_32.dll") != 0)
            continue;
        oft = (IMAGE_THUNK_DATA *)(base + (imp->OriginalFirstThunk ? imp->OriginalFirstThunk : imp->FirstThunk));
        ft = (IMAGE_THUNK_DATA *)(base + imp->FirstThunk);
        for (; oft->u1.AddressOfData; oft++, ft++) {
            void **slot = (void **)&ft->u1.Function;
            void *hook = NULL;
            const char *fn = NULL;
            int ord = 0;
            DWORD old;
            if (IMAGE_SNAP_BY_ORDINAL(oft->u1.Ordinal))
                ord = (int)IMAGE_ORDINAL(oft->u1.Ordinal);
            else
                fn = (const char *)((IMAGE_IMPORT_BY_NAME *)(base + oft->u1.AddressOfData))->Name;
            if ((fn && !strcmp(fn, "sendto")) || ord == 20) {
                real_sendto = (sendto_t)*slot;
                hook = (void *)h_sendto;
            } else if ((fn && !strcmp(fn, "recvfrom")) || ord == 17) {
                real_recvfrom = (recvfrom_t)*slot;
                hook = (void *)h_recvfrom;
            } else if ((fn && !strcmp(fn, "bind")) || ord == 2) {
                real_bind = (bind_t)*slot;
                hook = (void *)h_bind;
            }
            if (hook && VirtualProtect(slot, sizeof *slot, PAGE_READWRITE, &old)) {
                *slot = hook;
                VirtualProtect(slot, sizeof *slot, old, &old);
                done++;
            }
        }
    }
    return done;
}

static HMODULE g_self;
typedef void *(__cdecl *create_t)(void *, void *);
static create_t real_create;
typedef int (__cdecl *myip_t)(char *, int);
static myip_t real_myip;

static void ensure_hooks(void)
{
    HMODULE org;
    if (g_hooked)
        return;
    g_hooked = 1;
    InitializeCriticalSection(&g_cs);
    load_config(g_self);
    g_token = GetTickCount() ^ GetCurrentProcessId();
    org = GetModuleHandleA("TGNetOrg.dll");
    if (!org)
        org = LoadLibraryA("TGNetOrg.dll");
    if (!org)
        return;
    real_create = (create_t)GetProcAddress(org, "TGNet_CreateUDPSocket");
    real_myip = (myip_t)GetProcAddress(org, "TGNet_Get_MyIPaddress");
    if (!g_enabled) {
        logf_("hole punching off (rkp2p.ini)");
        return;
    }
    if (patch_iat(org) != 3 || !real_sendto || !real_recvfrom || !real_bind) {
        logf_("TGNetOrg.dll imports not found; hole punching off");
        g_enabled = 0;
    }
}

__declspec(dllexport) void *__cdecl TGNet_CreateUDPSocket(void *a, void *b)
{
    ensure_hooks();
    return real_create ? real_create(a, b) : NULL;
}

/* The host puts this address in its own player slot (Rhakmu.exe 0x44D8CE) and sends it to
 * everyone who joins; the joiners then talk to the host ONLY at that address. The original
 * returns the first adapter of gethostname(), often the Radmin VPN 26.x address: when Radmin
 * is not connected between the two PCs the join itself works (lobby address) but every later
 * packet goes to 26.x and is lost, and after ~10 s the host drops the joiner ("응답이 없어
 * 목록에서 제거"). While hole punching is on, report the address the lobby server sees, which
 * is also the address the lobby gives the other players. */
__declspec(dllexport) int __cdecl TGNet_Get_MyIPaddress(char *buf, int size)
{
    static u_long logged;
    int r;
    ensure_hooks();
    r = real_myip ? real_myip(buf, size) : 0;
    if (!buf || size < 16 || !g_hooked)
        return r;
    EnterCriticalSection(&g_cs);
    /* only an internet address: on Radmin 26.x / Hamachi 25.x the game's own choice stays */
    if (g_enabled && g_hello_ok && g_pub_ip && ((unsigned char *)&g_pub_ip)[0] != 26
        && ((unsigned char *)&g_pub_ip)[0] != 25) {
        char a[20];
        ipstr(g_pub_ip, a);
        if (logged != g_pub_ip) {
            logged = g_pub_ip;
            logf_("game address %s -> %s (as the server sees us)", r ? buf : "?", a);
        }
        lstrcpynA(buf, a, size);
        r = 1;
    }
    LeaveCriticalSection(&g_cs);
    return r;
}

BOOL WINAPI DllMain(HINSTANCE h, DWORD reason, LPVOID r)
{
    (void)r;
    if (reason == DLL_PROCESS_ATTACH) {
        g_self = h;
        DisableThreadLibraryCalls(h);
    }
    return TRUE;
}
