# 포트폴리오 요약

## 프로젝트 목표

국토교통부 대중교통 API 3종을 자동 수집하고, 품질 검증·정제·증분 적재·분석·
HTML 대시보드 생성까지 재현 가능한 운영형 데이터 파이프라인으로 구현했다.

## 아키텍처와 데이터 흐름

```text
공공데이터 API(JSON)
        ↓
src.collect_data
  재시도·원자적 저장·SHA-256 매니페스트
        ↓
src.inspect_data / src.clean_data
  컬럼·결측·중복·범위·인코딩 검증
        ↓
SQLite 증분 upsert
  transport_usage / transport_person / transport_hourly
  pipeline_runs / collection_runs
        ↓
src.analyze
  전국·부산 지역·교통수단·월별·시간대 분석
        ↓
src.dashboard
  HTML 대시보드·그래프·운영 상태
```

PostgreSQL과 Docker Compose 실행 구성도 제공해 SQLite 개발 환경과
PostgreSQL 운영 환경을 모두 재현할 수 있다.

## 운영 설계

- API 호출 실패: 최대 3회 재시도, 기존 파일 보존
- 대용량 API: `perPage=10000`으로 페이지 요청 수 절감
- 파일 무결성: 임시 `.part` 파일과 SHA-256 기록
- 중복 방지: 데이터셋별 자연키 unique index와 upsert
- 이력 관리: 수집·적재 성공/실패·시각·행 수·오류 기록
- 장애 통보: Discord 웹훅 또는 SMTP 이메일
- 복구 방식: 실패 단계 로그 확인 후 동일 파이프라인 재실행

## 검증 결과

현재 데이터 기준으로 다음 행을 수집·정제·적재했다.

| 테이블 | 행 수 |
|---|---:|
| `transport_usage` | 315,505 |
| `transport_person` | 96,366 |
| `transport_hourly` | 1,843,188 |

품질 검증에서 결측값과 완전 중복 행은 없었으며, Python 집계와 SQL 집계가
일치하도록 검증한다. 자동화 테스트는 수집, 정제, 품질, 분석, upsert,
실패 이력, 알림 무설정 상태를 포함한다.

## 분석 인사이트

- 부산 지역별 이용량은 부산진구·해운대구 등 주요 생활·환승권에 집중된다.
- 도시철도와 시내버스가 부산 이용량의 큰 비중을 차지하며 구·군별 교통수단
  구성 차이가 확인된다.
- 월별·계절별·시간대별 흐름을 함께 제공해 단순 연간 순위보다 수요 변동을
  파악할 수 있다.
- 이용량과 이용인원은 서로 다른 원천 집계이므로 동일 지표로 해석하지 않는다.

## 재현 명령

```powershell
python -m pytest -q
python -m src.run_pipeline
```

결과물은 `reports/dashboard.html`, 실행 로그는 `logs/pipeline.log`, 운영
이력은 `data/processed/transport_usage.sqlite`에서 확인한다.
