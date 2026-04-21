import sys
sys.path.insert(0, "core")
from collect import query_virustotal, query_shodan, query_censys

TEST_DOMAIN = "geodatatool.com"
TEST_IP_SHODAN = "8.8.8.8"
TEST_IP_CENSYS = "8.8.8.8"

print("Test query_virustotal...")
result_vt = query_virustotal(TEST_DOMAIN, "domain")
if result_vt:
    print(f"  OK : {result_vt}")
else:
    print("  ERREUR : query_virustotal a retourné None")

print("Test query_shodan...")
result_shodan = query_shodan(TEST_IP_SHODAN)
if result_shodan:
    print(f" OK : {result_shodan}")
else:
    print("  ERREUR : query_shodan a retourné None")

print("Test query_censys...")
result_censys = query_censys(TEST_IP_CENSYS)
if result_censys:
    print(f"  OK : {result_censys}")
else:
    print("  ERREUR : query_censys a retourné None")


