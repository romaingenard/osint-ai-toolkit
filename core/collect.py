import os
import time

import requests
import shodan
from dotenv import load_dotenv


load_dotenv()
VT_API_KEY = os.getenv("VT_API_KEY")
SHODAN_API_KEY = os.getenv("SHODAN_API_KEY")
CENSYS_API_KEY = os.getenv("CENSYS_API_TOKEN")


# Mapping ioc_type interne → segment de l'API VirusTotal v3.
# Remplace l'ancien `f"{ioc_type}s"` qui produisait "ips" pour
# ioc_type="ip_address" (endpoint inexistant : l'API attend "ip_addresses").
# VT v3 reference : https://docs.virustotal.com/reference/overview
VT_TYPE_SEGMENTS = {
    "domain": "domains",
    "file": "files",
    "ip_address": "ip_addresses",
    "url": "urls",
}


def query_virustotal(ioc, ioc_type):
    segment = VT_TYPE_SEGMENTS.get(ioc_type)
    if segment is None:
        print(
            f"Erreur VirusTotal : ioc_type '{ioc_type}' non supporté. "
            f"Valeurs acceptées : {sorted(VT_TYPE_SEGMENTS)}"
        )
        return None
    url = f"https://www.virustotal.com/api/v3/{segment}/{ioc}"
    headers = {"x-apikey": VT_API_KEY}
    try:
        response = requests.get(url, headers=headers)
        data = response.json()
        result = {
            "ioc": ioc,
            "source": "virustotal",
            "malicious": data.get("data", {}).get("attributes", {}).get("last_analysis_stats", {}).get("malicious", 0),
            "suspicious": data.get("data", {}).get("attributes", {}).get("last_analysis_stats", {}).get("suspicious", 0),
            "registrar": data.get("data", {}).get("attributes", {}).get("registrar", None),
            "permalink": f"https://www.virustotal.com/gui/{segment}/{ioc}",
        }
        time.sleep(1)
        return result
    except Exception as e:
        print(f"Erreur VirusTotal : {e}")
        return None
    

def query_shodan(ip):
    try:
        api = shodan.Shodan(SHODAN_API_KEY)
        host = api.host(ip)
        result = {
            "ioc": ip,
            "source": "shodan",
            "org": host.get("org", None),
            "asn": host.get("asn", None),
            "ports": host.get("ports", []),
            "country": host.get("country_name", None),
            "permalink": f"https://www.shodan.io/host/{ip}",
        }
        time.sleep(1)
        return result
    except Exception as e:
        print(f"Erreur Shodan : {e}")
        return None

def query_censys(ip):
    try:
        url = f"https://search.censys.io/api/v2/hosts/{ip}"
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {CENSYS_API_KEY}"
        }
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        data = response.json()
        host = data.get("result", {})
        services = host.get("services", [])
        ports = [s.get("port") for s in services]
        result = {
            "ioc" :ip,
            "source": "censys",
            "org": host.get("autonomous_system", {}).get("name", None),
            "asn": host.get("autonomous_system", {}).get("asn", None),
            "ports": ports,
            "country": host.get("location", {}).get("country", None),
            "permalink": f"https://search.censys.io/hosts/{ip}"
        }
        time.sleep(1)
        return result
    except Exception as e:
        print(f"Erreur Censys : {e}")
        return None


