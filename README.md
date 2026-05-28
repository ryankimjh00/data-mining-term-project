# TMDB 인기 영화 CSV 수집

TMDB API로 인기 영화 목록과 영화별 상세 정보를 가져와 CSV 파일로 저장하는 간단한 Python 프로그램입니다.

## API 키 준비

TMDB의 `authentication/token/new`, `authentication/session/new` 엔드포인트는 API 키 발급용이 아니라 사용자 승인 세션용입니다. 영화 목록 조회에는 계정 설정의 API 메뉴에서 발급한 `API Key` 또는 `API Read Access Token`이 필요합니다.

1. TMDB에 로그인합니다.
2. 계정 설정에서 `API` 메뉴로 이동합니다.
3. API Key 또는 API Read Access Token을 발급받습니다.
4. 아래 명령으로 키를 파일에 저장합니다.

```bash
python3 src/fetch_popular_movies.py --init-key
```

기본 저장 위치는 `config/tmdb_token.txt`입니다. 이 파일은 외부에 공유하지 마세요.

## 실행

```bash
python3 src/fetch_popular_movies.py --pages 5 --language ko-KR --output data/popular_movies.csv
```

기본 실행은 인기 목록 API로 영화 ID를 가져온 뒤, 각 영화의 상세 API를 추가 호출해 제작비, 수익, 런타임, 제작사, 주요 출연진, 감독, 키워드까지 저장합니다.
KOBIS 조인을 하지 않으면 `kobis_match_status`는 `pending`으로 저장되어 이후 CSV 기준 매핑 작업에 사용할 수 있습니다.

KOBIS API 제한이 있을 때 한국 영화 TMDB 목록만 먼저 만들려면:

```bash
python3 src/fetch_popular_movies.py --korean-only --pages 5 --language ko-KR --output data/tmdb_korean_movies.csv
```

성인 비디오성 영화를 제외하고 300개를 먼저 만들려면:

```bash
python3 src/fetch_popular_movies.py --korean-only --exclude-adult-like --pages 50 --limit 300 --language ko-KR --output data/tmdb_korean_movies.csv
```

한국 영화만 가져오고 KOBIS 관객수 데이터를 붙이려면:

```bash
python3 src/fetch_popular_movies.py --korean-only --join-kobis --pages 5 --output data/korean_popular_movies.csv
```

KOBIS 키 기본 경로는 `config/kobis_key.txt`입니다.
`kobis_audi_acc`는 KOBIS 일별 박스오피스에서 발견한 가장 큰 누적 관객수입니다. 기본값은 개봉일부터 60일간 탐색하므로, 장기 흥행작은 `--kobis-scan-days 120`처럼 늘려 실행할 수 있습니다.

기존 TMDB CSV를 원본으로 두고 KOBIS 매핑 결과를 별도 CSV에 저장하려면:

```bash
python3 src/fetch_popular_movies.py --input data/tmdb_korean_movies.csv --join-kobis --output data/tmdb_korean_movies_kobis.csv
```

이 모드는 한 영화 처리 후마다 결과 CSV를 저장합니다. API 제한으로 중단되면 같은 명령을 다시 실행해 `pending` 상태부터 이어서 처리합니다. KOBIS 영화가 없으면 KOBIS 필드는 `null`, `kobis_match_status`는 `not_found`로 저장합니다. 영화코드는 찾았지만 박스오피스 누적 관객수를 찾지 못하면 `matched_no_boxoffice`로 저장합니다.

옵션:

- `--pages`: 가져올 페이지 수입니다. 페이지당 20개 영화가 반환됩니다.
- `--limit`: 필터링 후 저장할 최대 영화 수입니다.
- `--language`: 응답 언어입니다. 예: `ko-KR`, `en-US`
- `--region`: 선택 지역 코드입니다. 예: `KR`, `US`
- `--output`: CSV 저장 경로입니다.
- `--input`: 기존 TMDB CSV를 읽어 KOBIS 조인만 수행할 때 사용할 입력 파일입니다.
- `--token-file`: 키 파일 경로입니다.
- `--cast-limit`: CSV에 저장할 주요 출연진 수입니다. 기본값은 10명입니다.
- `--basic-only`: 상세 API 호출 없이 인기 목록 기본 정보만 저장합니다.
- `--korean-only`: TMDB에서 한국어 원어 영화만 인기도순으로 가져옵니다.
- `--exclude-adult-like`: 성인 비디오성 영화로 보이는 항목을 제목과 TMDB 키워드 기준으로 제외합니다.
- `--join-kobis`: KOBIS 영화코드와 박스오피스 관객수 데이터를 조인합니다.
- `--kobis-key-file`: KOBIS 키 파일 경로입니다.
- `--kobis-scan-days`: KOBIS 누적 관객수 탐색을 위해 개봉일부터 스캔할 일수입니다. 기본값은 60일입니다.
- `--quiet`: 진행 로그 없이 실행합니다.

실행 중에는 목록 페이지 요청, 영화별 상세 조회, CSV 저장 단계가 터미널에 표시됩니다.

환경 변수 `TMDB_READ_ACCESS_TOKEN` 또는 `TMDB_API_KEY`를 설정하면 키 파일보다 우선 사용합니다.
환경 변수 `KOBIS_API_KEY`를 설정하면 KOBIS 키 파일보다 우선 사용합니다.

## KOBIS 연도별 박스오피스 CSV 수집

KOBIS 공식통계 연도별 박스오피스 화면에서 조회기간과 국적을 설정해 결과 전체를 CSV로 저장합니다. 기본 국적은 한국입니다.

```bash
python3 src/kobis_yearly_boxoffice_crawler.py --year 2022 --output data/kobis_yearly_boxoffice_korean_2022.csv
```

전체 조회기간을 한 번에 수집하려면:

```bash
python3 src/kobis_yearly_boxoffice_crawler.py --all-years --output data/kobis_yearly_boxoffice_korean_all_years.csv
```

## KOBIS/TMDB 제목 매핑

```bash
python3 src/map_kobis_tmdb_titles.py --kobis data/kobis_yearly_boxoffice_korean_all_years.csv --tmdb data/tmdb_korean_movies.csv --output data/kobis_tmdb_title_matches.csv
```

## 포스터 다운로드

```bash
python3 src/download_posters.py --input data/kobis_tmdb_title_matches.csv --output-dir data/posters
```

## 폴더 구조

- `src/`: 데이터 수집, 매핑, 포스터 다운로드 스크립트
- `data/processed/`: 전처리 산출물
- `data/posters/`: 포스터 이미지 산출물
- `notebooks/`: EDA 및 모델링 노트북
- `outputs/figures/`, `outputs/metrics/`: 시각화와 성능 지표 산출물
