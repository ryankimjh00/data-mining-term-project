# 국내 영화 흥행 여부 예측 및 성공 요인 분석 구현 계획

## 1. 프로젝트 주제

국내 영화 흥행 여부 예측 및 성공 요인 분석: 영화 제목, 포스터, 메타데이터를 중심으로

## 2. 핵심 질문

- 영화 메타데이터만으로 흥행 여부를 예측할 수 있는가?
- 영화 제목 특성을 추가하면 예측 성능이 향상되는가?
- 포스터 이미지 특성을 추가하면 예측 성능이 향상되는가?
- 흥행에 가장 큰 영향을 주는 요인은 무엇인가?

## 3. 데이터 구성

### 3.1 메인 데이터

- `data/kobis_tmdb_title_matches.csv`
- KOBIS 관객 수 데이터와 TMDB 영화 메타데이터가 제목 기준으로 매칭된 데이터
- 현재 기준 약 654건

### 3.2 보조 데이터

- `data/tmdb_korean_movies.csv`
- `data/tmdb_korean_movies_kobis.csv`
- `data/kobis_yearly_boxoffice_korean_all_years.csv`

### 3.3 주요 컬럼

| 구분 | 컬럼 예시 |
| --- | --- |
| 흥행 정보 | `audience_count`, `sales_amount`, `screen_count` |
| 기본 정보 | `match_title`, `open_date`, `tmdb_runtime`, `tmdb_release_year` |
| 장르 정보 | `tmdb_genres`, `tmdb_genre_ids` |
| 제작 정보 | `tmdb_production_companies`, `tmdb_directors`, `tmdb_cast` |
| TMDB 정보 | `tmdb_popularity`, `tmdb_vote_average`, `tmdb_vote_count` |
| 이미지 정보 | `tmdb_poster_url` |

## 4. 타깃 변수 설계

### 4.1 기본 분류 타깃

누적 관객 수 300만 명 이상 여부를 기본 흥행 기준으로 설정한다.

```python
is_success = audience_count >= 3_000_000
```

### 4.2 보조 분류 타깃

민감도 분석을 위해 흥행 기준을 다르게 설정한 실험도 수행한다.

- 100만 명 이상
- 300만 명 이상
- 500만 명 이상

### 4.3 회귀 타깃

누적 관객 수는 분포가 한쪽으로 치우칠 가능성이 높으므로 로그 변환을 적용한다.

```python
target = log1p(audience_count)
```

## 5. 전처리 계획

### 5.1 수치형 변수

- `audience_count`, `sales_amount`, `screen_count`, `tmdb_runtime`
- 결측치 처리
- 이상치 확인
- 필요 시 로그 변환
- K-NN, Logistic Regression, DNN 사용 시 스케일링 적용

### 5.2 범주형 변수

- 장르
- 감독
- 주요 배우
- 제작사

처리 방식:

- 장르는 다중 라벨 원-핫 인코딩
- 감독, 배우, 제작사는 빈도 기반 변수로 단순화
- 희소한 범주는 `other` 처리

### 5.3 날짜형 변수

`open_date`에서 다음 변수를 추출한다.

- 개봉 연도
- 개봉 월
- 계절
- 여름 성수기 여부
- 겨울 성수기 여부
- 연말 개봉 여부

### 5.4 제목 특성

`match_title`에서 다음 특성을 추출한다.

| 특성 | 설명 |
| --- | --- |
| 제목 길이 | 공백 제외 글자 수 |
| 단어 수 | 공백 기준 토큰 수 |
| 숫자 포함 여부 | 숫자가 포함되면 1 |
| 영어 포함 여부 | 영문자가 포함되면 1 |
| 특수문자 포함 여부 | 콜론, 괄호, 하이픈 등 |
| 시리즈 키워드 여부 | 2, 3, 리턴즈, 비긴즈 등 |
| 감성/장르 키워드 여부 | 사랑, 전쟁, 범죄, 살인, 가족 등 |

### 5.5 포스터 특성

`tmdb_poster_url`을 이용해 포스터 이미지를 다운로드한 뒤 다음 특성을 추출한다.

| 특성 | 설명 |
| --- | --- |
| 평균 밝기 | 전체 포스터의 명도 평균 |
| 평균 채도 | 색감의 강도 |
| RGB 평균 | R, G, B 채널 평균 |
| 대비 | 밝기 표준편차 |
| 에지 밀도 | 포스터 복잡도 |
| 이미지 비율 | 가로/세로 비율 |

포스터 다운로드 경로:

```text
data/posters/
```

포스터 특성 저장 경로:

```text
data/processed/poster_features.csv
```

## 6. 모델 구성

### 6.1 분류 모델

| 모델 | 역할 |
| --- | --- |
| Logistic Regression | 기본 분류 모델, 계수 해석 |
| Decision Tree | 규칙 기반 해석 |
| Random Forest | 주요 성능 모델, 변수 중요도 분석 |
| DNN | 전체 특성의 비선형 결합 실험 |

### 6.2 회귀 모델

| 모델 | 역할 |
| --- | --- |
| Linear Regression | 기본 회귀 기준 모델 |
| Ridge Regression | 규제 효과 확인 |
| Lasso Regression | 변수 선택 효과 확인 |
| Random Forest Regressor | 비선형 회귀 모델 |

### 6.3 보조 분석

- PCA: 흥행/비흥행 영화의 분포 시각화
- Clustering: 유사 영화 군집별 평균 관객 수 비교
- Hyperparameter Tuning: Random Forest, Decision Tree, Ridge/Lasso 중심

## 7. 실험 설계

제목과 포스터 특성이 실제로 성능 향상에 기여하는지 확인하기 위해 Ablation Study를 수행한다.

| 실험 | 입력 특성 |
| --- | --- |
| A | 메타데이터만 |
| B | 메타데이터 + 제목 특성 |
| C | 메타데이터 + 포스터 특성 |
| D | 메타데이터 + 제목 특성 + 포스터 특성 |

핵심 분석 방향:

- 제목 특성 추가 전후 성능 비교
- 포스터 특성 추가 전후 성능 비교
- 메타데이터 대비 비정형 특성의 보조 효과 확인

## 8. 평가 지표

### 8.1 분류 평가

- Accuracy
- Precision
- Recall
- F1-score
- ROC-AUC
- Confusion Matrix

클래스 불균형 가능성이 있으므로 Accuracy보다 F1-score, Recall, ROC-AUC를 중요하게 본다.

### 8.2 회귀 평가

- MAE
- RMSE
- R2
- RMSLE

로그 변환을 사용한 경우 예측값을 원래 관객 수 단위로 복원해 해석한다.

## 9. 시각화 계획

| 그래프 | 목적 |
| --- | --- |
| 누적 관객 수 분포 | 데이터 불균형 확인 |
| 흥행/비흥행 클래스 비율 | 분류 문제 난이도 확인 |
| 장르별 평균 관객 수 | 장르 영향 분석 |
| 개봉 월별 평균 관객 수 | 개봉 시기 영향 분석 |
| 제목 길이별 흥행률 | 제목 특성 분석 |
| 포스터 밝기/채도별 흥행률 | 포스터 특성 분석 |
| 모델별 성능 비교 | 모델 간 성능 차이 확인 |
| Confusion Matrix | 오분류 구조 분석 |
| Feature Importance | 흥행 성공 요인 분석 |
| PCA 2D Scatter | 영화 분포 시각화 |

## 10. 구현 파일 구조

```text
TMDB/
  data/
    processed/
    posters/
  docs/
    movie-success-prediction-plan.md
  notebooks/
    01_eda.ipynb
    02_preprocessing.ipynb
    03_model_classification.ipynb
    04_model_regression.ipynb
    05_result_analysis.ipynb
  src/
    preprocessing.py
    feature_title.py
    feature_poster.py
    train_classification.py
    train_regression.py
    evaluate.py
  outputs/
    figures/
    metrics/
  requirements.txt
```

## 11. 구현 순서

1. `requirements.txt` 작성
2. EDA 노트북 작성
3. 전처리 및 제목 특성 추출 코드 작성
4. 포스터 다운로드 및 이미지 특성 추출 코드 작성
5. 분류 모델 3종 구현
6. Ablation Study 실행
7. 회귀 모델 구현
8. Feature Importance 및 오분류 분석
9. PCA 또는 Clustering 보조 분석
10. 보고서용 표와 그래프 정리

## 12. 우선순위

| 우선순위 | 작업 |
| --- | --- |
| 1 | 흥행 여부 분류 모델 완성 |
| 2 | 제목 특성 추가 실험 |
| 3 | 포스터 특성 추가 실험 |
| 4 | Random Forest 변수 중요도 분석 |
| 5 | 회귀 예측 |
| 6 | DNN, PCA, Clustering 보조 분석 |

## 13. 주의사항

- 천만 관객 여부만 타깃으로 설정하지 않는다.
- 클래스 불균형을 반드시 확인한다.
- 개봉 전 예측 실험에서는 개봉 후에만 알 수 있는 변수 사용을 제한한다.
- `tmdb_vote_average`, `tmdb_vote_count`, `tmdb_popularity`는 성공 요인 분석 실험에서는 사용할 수 있지만, 개봉 전 예측 실험에서는 데이터 누수 가능성을 명시한다.
- 임시 코드, 불필요한 출력, 디버깅 로그는 제거한다.
- 결과 해석에서는 성능 수치뿐 아니라 모델별 특성과 한계를 함께 설명한다.

## 14. 최종 산출물

- 전처리 완료 데이터
- 제목 특성 데이터
- 포스터 이미지 특성 데이터
- 모델별 성능 비교표
- 주요 시각화 그래프
- Feature Importance 분석 결과
- 오분류 사례 분석
- 보고서 작성용 결론 정리

