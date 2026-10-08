"""Replace only target aliases; preserve unrelated mappings and comments."""
import ipaddress

def replace_entries(content, ip, domains):
    ip = str(ipaddress.IPv4Address(ip))
    targets = {d.lower() for d in domains}
    lines = []
    for line in content.splitlines(keepends=True):
        body, separator, comment = line.partition('#')
        fields = body.split()
        if len(fields) < 2 or not any(d.lower() in targets for d in fields[1:]):
            lines.append(line)
            continue
        others = [d for d in fields[1:] if d.lower() not in targets]
        if others:
            lines.append(fields[0] + '\t' + ' '.join(others) + (' #' + comment.rstrip('\r\n') if separator else '') + '\n')
        elif separator:
            lines.append('#' + comment.rstrip('\r\n') + '\n')
    result = ''.join(lines)
    if result and not result.endswith('\n'):
        result += '\n'
    return result + ''.join(f'{ip} {domain}\n' for domain in dict.fromkeys(domains))
