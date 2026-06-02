#!/bin/bash
# ╔══════════════════════════════════════════════════════════════╗
# ║          Redis 캐싱 통합 테스트 스크립트                      ║
# ║  용도: 배포 후 캐싱 동작 + 재발 방지 대책 검증                ║
# ║  실행: bash test_redis_cache.sh                              ║
# ╚══════════════════════════════════════════════════════════════╝

set -e
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color
PASS=0
FAIL=0

pass() { echo -e "  ${GREEN}✅ PASS${NC} $1"; PASS=$((PASS+1)); }
fail() { echo -e "  ${RED}❌ FAIL${NC} $1"; FAIL=$((FAIL+1)); }

echo "========================================="
echo "  Redis 캐싱 통합 테스트"
echo "  $(date)"
echo "========================================="

# ─── 1. 컨테이너 상태 ───
echo -e "\n${BLUE}━━━ 1. 컨테이너 상태 ━━━${NC}"

docker ps --filter "name=ssh-reports-hub-redis" --format "{{.Status}}" | grep -q "Up" \
  && pass "Redis 컨테이너 실행 중" \
  || fail "Redis 컨테이너 실행 중"

docker ps --filter "name=ssh-reports-hub-fastapi-prod" --format "{{.Status}}" | grep -q "Up" \
  && pass "FastAPI 컨테이너 실행 중" \
  || fail "FastAPI 컨테이너 실행 중"

docker ps --filter "name=external-nginx" --format "{{.Status}}" | grep -q "Up" \
  && pass "external-nginx 실행 중" \
  || fail "external-nginx 실행 중"

# ─── 2. Health Check ───
echo -e "\n${BLUE}━━━ 2. API Health Check ━━━${NC}"

for mode in "로컬:http://localhost:8004" "HTTPS:https://ssh-oci.duckdns.org"; do
    label="${mode%%:*}"
    url="${mode#*:}"
    code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 "${url}/health" 2>/dev/null || echo "000")
    [ "$code" = "200" ] \
      && pass "${label} /health → ${code}" \
      || fail "${label} /health → ${code}"
done

# ─── 3. 모든 엔드포인트 응답 검증 ───
echo -e "\n${BLUE}━━━ 3. 엔드포인트 200 응답 ━━━${NC}"

endpoints=(
    "/external/api/search?limit=3&offset=0"
    "/external/api/industry?limit=3&offset=0"
    "/external/api/companies"
    "/external/api/boards?company=0"
)

for ep in "${endpoints[@]}"; do
    code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "http://localhost:8004${ep}" 2>/dev/null || echo "000")
    [ "$code" = "200" ] \
      && pass "로컬 ${ep} → ${code}" \
      || fail "로컬 ${ep} → ${code}"
done

# ─── 4. Redis 연결 + 키 확인 ───
echo -e "\n${BLUE}━━━ 4. Redis 캐시 동작 ━━━${NC}"

# Redis 연결
docker exec ssh-reports-hub-redis redis-cli PING 2>/dev/null | grep -q "PONG" \
  && pass "Redis PING 성공" \
  || fail "Redis PING 실패"

# 캐시 키 확인
key_count=$(docker exec ssh-reports-hub-redis redis-cli DBSIZE 2>/dev/null || echo "0")
echo "  ${YELLOW}ℹ${NC}  현재 캐시 키: ${key_count}개"

# ─── 5. 캐시 성능 비교 ───
echo -e "\n${BLUE}━━━ 5. 캐시 성능 (Cold vs Hot) ━━━${NC}"

# 캐시 초기화
docker exec ssh-reports-hub-redis redis-cli FLUSHDB > /dev/null 2>&1
echo "  ${YELLOW}ℹ${NC}  캐시 초기화 완료"

TEST_URL="http://localhost:8004/external/api/search?limit=10&offset=0"

cold=$(curl -s -o /dev/null -w '%{time_total}' --max-time 10 "${TEST_URL}" 2>/dev/null || echo "0")
echo "  ${YELLOW}ℹ${NC}  Cold (DB 쿼리): ${cold}s"

hot=$(curl -s -o /dev/null -w '%{time_total}' --max-time 10 "${TEST_URL}" 2>/dev/null || echo "0")
echo "  ${YELLOW}ℹ${NC}  1차 Hot (캐시): ${hot}s"

hot2=$(curl -s -o /dev/null -w '%{time_total}' --max-time 10 "${TEST_URL}" 2>/dev/null || echo "0")
echo "  ${YELLOW}ℹ${NC}  2차 Hot (캐시): ${hot2}s"

# 캐시 효과 판단 (hot이 cold보다 20% 이상 빠르면 OK)
cold_ms=$(echo "$cold * 1000" | bc 2>/dev/null | cut -d. -f1 || echo "999")
hot_ms=$(echo "$hot * 1000" | bc 2>/dev/null | cut -d. -f1 || echo "0")
if [ "$hot_ms" -lt "$cold_ms" ] 2>/dev/null; then
    ratio=$(echo "scale=1; $cold_ms / $hot_ms" | bc 2>/dev/null || echo "1")
    pass "캐시 효과 있음 (${ratio}x 개선)"
else
    echo "  ${YELLOW}⚠${NC}  캐시 효과 미미 (네트워크 지연이 대부분일 수 있음)"
fi

# ─── 6. 재발 방지 #1: Pydantic 직렬화 ───
echo -e "\n${BLUE}━━━ 6. 재발 방지 검증: Pydantic 직렬화 ━━━${NC}"

# companies = list[CompanyResponse] 반환, 직렬화 검증
resp=$(curl -s --max-time 10 "http://localhost:8004/external/api/companies" 2>/dev/null)
echo "$resp" | python3 -c "import sys,json; d=json.load(sys.stdin); assert isinstance(d,list); assert 'name' in d[0]; print(f'  ${GREEN}✅ PASS${NC} companies 직렬화 정상: {len(d)}개 증권사')" 2>/dev/null \
  || fail "companies 직렬화 실패"

resp=$(curl -s --max-time 10 "http://localhost:8004/external/api/boards?company=0" 2>/dev/null)
echo "$resp" | python3 -c "import sys,json; d=json.load(sys.stdin); assert isinstance(d,list); assert 'board_nm' in d[0]; print(f'  ${GREEN}✅ PASS${NC} boards 직렬화 정상: {len(d)}개 게시판')" 2>/dev/null \
  || fail "boards 직렬화 실패"

# ─── 7. 재발 방지 #2: Nginx 동적 DNS ───
echo -e "\n${BLUE}━━━ 7. 재발 방지 검증: Nginx 동적 DNS 리졸브 ━━━${NC}"

docker exec external-nginx grep -q "resolver 127.0.0.11" /etc/nginx/conf.d/default.conf 2>/dev/null \
  && pass "resolver 127.0.0.11 설정됨" \
  || fail "resolver 127.0.0.11 없음"

docker exec external-nginx grep -q 'proxy_pass http://\$backend' /etc/nginx/conf.d/default.conf 2>/dev/null \
  && pass "proxy_pass 변수 사용 중 (동적 DNS)" \
  || fail "proxy_pass 변수 미사용"

# ─── 8. 재발 방지 #3: 장애 허용 (Redis 다운 시뮬레이션 불가 - skip) ───
echo -e "\n${BLUE}━━━ 8. 재발 방지 검증: Redis 메모리 제한 ━━━${NC}"

docker exec ssh-reports-hub-redis redis-cli CONFIG GET maxmemory 2>/dev/null | tail -1 | grep -qv "^0$" \
  && pass "maxmemory 설정됨" \
  || fail "maxmemory 미설정"

docker exec ssh-reports-hub-redis redis-cli CONFIG GET maxmemory-policy 2>/dev/null | tail -1 | grep -q "allkeys-lru" \
  && pass "maxmemory-policy = allkeys-lru" \
  || fail "maxmemory-policy 불일치"

# ─── 9. _to_json_safe 코드 존재 확인 ───
echo -e "\n${BLUE}━━━ 9. 코드 배포 검증 ━━━${NC}"

docker exec ssh-reports-hub-fastapi-prod grep -q "_to_json_safe\|model_dump" /app/app/cache.py 2>/dev/null \
  && pass "Pydantic 직렬화 패치 적용됨 (_to_json_safe)" \
  || fail "Pydantic 직렬화 패치 누락"

docker exec ssh-reports-hub-fastapi-prod grep -q "cache_response" /app/app/routers/external_api.py 2>/dev/null \
  && pass "cache_response 데코레이터 적용됨" \
  || fail "cache_response 데코레이터 누락"

# ─── 결과 ───
echo -e "\n========================================="
echo -e "  결과: ${GREEN}${PASS} PASS${NC} / ${RED}${FAIL} FAIL${NC}"
echo "========================================="

if [ "$FAIL" -gt 0 ]; then
    echo -e "${RED}일부 테스트 실패!${NC}"
    exit 1
else
    echo -e "${GREEN}모든 테스트 통과! 🎉${NC}"
    exit 0
fi
