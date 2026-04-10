import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import os

# Import data transformation module for new MOLIT API format support
from data_transformer import auto_transform, detect_format, detect_property_type, normalize_officetel

# 페이지 설정
st.set_page_config(
    page_title="아파트 실거래가 분석 대시보드",
    page_icon="🏢",
    layout="wide"
)

# 년월을 한글 형식으로 변환하는 함수
def format_yearmonth_korean(yearmonth_str):
    """년월 문자열을 한글 형식으로 변환 (예: '2025-01' -> '2025년 1월')"""
    try:
        if '-' in yearmonth_str:
            year, month = yearmonth_str.split('-')
            return f"{year}년 {int(month)}월"
        return yearmonth_str
    except:
        return yearmonth_str

# 계약년월을 한글 형식으로 변환하는 함수
def format_contract_yearmonth(yearmonth):
    """계약년월 숫자를 한글 형식으로 변환 (예: 202511 -> '2025년 11월')"""
    try:
        yearmonth_str = str(yearmonth)
        if len(yearmonth_str) == 6:  # YYYYMM 형식
            year = yearmonth_str[:4]
            month = int(yearmonth_str[4:6])
            return f"{year}년 {month}월"
        elif len(yearmonth_str) == 4:  # YYYYMM 형식이지만 숫자로 표시된 경우
            # 이미 처리된 형식일 수 있음
            return yearmonth_str
        return yearmonth_str
    except:
        return str(yearmonth)

# 금액 축 레이블을 한글로 변환하는 함수
def format_price_axis(fig, axis='y', max_value=None):
    """차트의 금액 축 레이블을 한글(억원) 형식으로 변환"""
    if max_value is None:
        # 차트에서 최대값 추정
        max_value = 300000  # 기본값
    
    # 틱 간격 계산 (만원 단위)
    if max_value <= 50000:
        dtick = 10000
    elif max_value <= 100000:
        dtick = 20000
    elif max_value <= 200000:
        dtick = 50000
    else:
        dtick = 100000
    
    # 틱 값 생성
    tickvals = list(range(0, int(max_value) + dtick, dtick))
    ticktext = []
    for val in tickvals:
        if val >= 10000:
            ticktext.append(f"{val//10000}억원")
        elif val > 0:
            ticktext.append(f"{val}만원")
        else:
            ticktext.append("0")
    
    if axis == 'x':
        fig.update_layout(
            xaxis=dict(
                tickmode='array',
                tickvals=tickvals,
                ticktext=ticktext
            )
        )
    elif axis == 'y':
        fig.update_layout(
            yaxis=dict(
                tickmode='array',
                tickvals=tickvals,
                ticktext=ticktext
            )
        )
    elif axis == 'y2':
        fig.update_layout(
            yaxis2=dict(
                tickmode='array',
                tickvals=tickvals,
                ticktext=ticktext
            )
        )
    return fig

# 데이터 로드 및 전처리 함수 (파일 경로용 - 캐시 사용)
@st.cache_data
def load_data_from_path(filepath):
    """파일 경로로부터 데이터 로드 (캐시 사용)"""
    try:
        df = pd.read_excel(filepath, sheet_name=0)
    except Exception as e:
        st.error(f"파일 로드 중 오류 발생: {str(e)}")
        raise

    # 부동산 유형 감지 및 정규화
    property_type = detect_property_type(df)
    st.session_state['property_type'] = property_type

    if property_type == "아파트매매":
        try:
            file_format = detect_format(df)
            if file_format == "new":
                df = auto_transform(df)
        except ValueError as e:
            st.error(f"파일 형식을 인식할 수 없습니다: {str(e)}")
            raise
    else:
        df = normalize_officetel(df, property_type)

    return preprocess_data(df, property_type)

# 데이터 전처리 함수
def preprocess_data(df, property_type="아파트매매"):
    """데이터프레임 전처리

    property_type: '아파트매매', '오피스텔매매', '오피스텔전월세'
    """

    # 0. 해제사유발생일이 있는 데이터(취소된 거래) 제외
    if '해제사유발생일' in df.columns:
        def is_cancelled(val):
            if pd.isna(val):
                return False
            val_str = str(val).strip()
            if val_str in ['-', '', 'nan', 'None']:
                return False
            return True

        cancelled_mask = df['해제사유발생일'].apply(is_cancelled)
        cancelled_count = cancelled_mask.sum()

        if cancelled_count > 0:
            df = df[~cancelled_mask].copy()
            st.session_state['cancelled_count'] = cancelled_count
        else:
            st.session_state['cancelled_count'] = 0
    else:
        st.session_state['cancelled_count'] = 0

    # 1. 거래금액(만원) 숫자 변환 (normalize_officetel에서 이미 처리되었을 수 있음)
    if '거래금액(만원)' in df.columns and df['거래금액(만원)'].dtype == 'object':
        df['거래금액(만원)'] = df['거래금액(만원)'].astype(str).str.replace(',', '').astype(int)

    # 2. 날짜 컬럼 생성 (계약년월 + 계약일)
    df['계약일_str'] = df['계약일'].astype(str).str.zfill(2)
    df['거래일자'] = pd.to_datetime(df['계약년월'].astype(str) + df['계약일_str'], format='%Y%m%d')

    # 3. 평수 계산 (전용면적 / 3.3)
    df['평수'] = pd.to_numeric(df['전용면적(㎡)'], errors='coerce') / 3.3

    # 4. 평당가 계산 (거래금액 / 평수) — 전월세는 보증금 기준
    if '거래금액(만원)' in df.columns:
        df['평당가(만원)'] = df['거래금액(만원)'] / df['평수']

    # 5. 전월세 전용: 월세 평당가
    if property_type == "오피스텔전월세" and '월세금(만원)' in df.columns:
        df['월세평당가(만원)'] = df['월세금(만원)'] / df['평수']

    return df

# 업로드된 파일 로드 함수 (캐시 사용 안 함)
def load_data_from_upload(uploaded_file):
    """업로드된 파일로부터 데이터 로드 (캐시 사용 안 함)

    - 부동산 유형 자동 감지 (아파트매매 / 오피스텔매매 / 오피스텔전월세)
    - 신규 MOLIT API 형식이면 레거시 형식으로 자동 변환
    - 오피스텔 파일이면 공통 형식으로 정규화 (건물명→단지명 등)
    """
    try:
        df = pd.read_excel(uploaded_file, sheet_name=0)
    except Exception as e:
        st.error(f"파일 로드 중 오류 발생: {str(e)}")
        raise

    # 부동산 유형 감지 (정규화 전에 먼저 감지)
    property_type = detect_property_type(df)
    st.session_state['property_type'] = property_type

    # 아파트: 신규 API 형식이면 레거시로 변환
    if property_type == "아파트매매":
        try:
            file_format = detect_format(df)
            if file_format == "new":
                df = auto_transform(df)
                st.session_state['file_format_converted'] = True
            else:
                st.session_state['file_format_converted'] = False
        except ValueError as e:
            st.error(f"파일 형식을 인식할 수 없습니다: {str(e)}")
            raise
    else:
        # 오피스텔: 공통 형식으로 정규화
        df = normalize_officetel(df, property_type)
        st.session_state['file_format_converted'] = False

    # 전처리
    return preprocess_data(df, property_type)

# 메인 함수
def main():
    title_map = {
        '아파트매매': "📊 아파트 실거래가 상세 분석",
        '오피스텔매매': "🏢 오피스텔 매매 실거래가 분석",
        '오피스텔전월세': "🏢 오피스텔 전월세 실거래 분석",
    }
    # 타이틀 placeholder: 파일 로드 후 올바른 유형으로 채움
    title_placeholder = st.empty()

    # 앱 시작 시 로컬 파일이 없으면 가장 첫 번째 xlsx 자동 선택
    if 'local_file_path' not in st.session_state:
        local_xlsx_all = sorted([f for f in os.listdir('.') if f.endswith('.xlsx') or f.endswith('.xls')])
        if local_xlsx_all:
            st.session_state['local_file_path'] = os.path.abspath(local_xlsx_all[0])

    # 파일 업로드 기능 (접을 수 있게)
    with st.sidebar.expander("📁 파일 업로드", expanded=False):
        uploaded_file = st.file_uploader(
            "Excel 파일 업로드",
            type=['xlsx', 'xls'],
            help="국토교통부 실거래가 공개시스템에서 다운로드한 Excel 파일을 업로드하세요\n(아파트/오피스텔 매매·전월세 모두 지원)"
        )

    # 로컬 파일 빠른 로드 버튼
    local_xlsx = sorted([f for f in os.listdir('.') if f.endswith('.xlsx') or f.endswith('.xls')])
    if local_xlsx:
        with st.sidebar.expander("📂 로컬 파일 불러오기", expanded=True):
            for fname in local_xlsx:
                if st.button(fname, key=f"local_{fname}", use_container_width=True):
                    st.session_state['local_file_path'] = os.path.abspath(fname)

    # 로컬 파일 경로가 선택된 경우 업로드 파일보다 우선
    local_path = st.session_state.get('local_file_path')

    # 파일이 업로드되었는지 확인
    if uploaded_file is not None or local_path:
        # 데이터 로드
        try:
            if uploaded_file is not None:
                df = load_data_from_upload(uploaded_file)
                display_name = uploaded_file.name
            else:
                df = load_data_from_path(local_path)
                display_name = os.path.basename(local_path)

            # 로드 후 property_type 확정
            property_type = st.session_state.get('property_type', '아파트매매')
            # 올바른 타이틀로 채우기
            title_placeholder.title(title_map.get(property_type, "📊 실거래가 상세 분석"))

            # 사이드바 상태 표시
            type_badge = {"아파트매매": "🏠 아파트 매매", "오피스텔매매": "🏢 오피스텔 매매", "오피스텔전월세": "🏢 오피스텔 전월세"}
            st.sidebar.info(type_badge.get(property_type, property_type))
            st.sidebar.success(f"✅ {display_name}")
            if st.session_state.get('file_format_converted', False):
                st.sidebar.info("신규 API 형식 자동 변환됨")
        except Exception as e:
            st.error(f"데이터 파일을 읽는 중 오류가 발생했습니다: {str(e)}\n\n필요한 패키지(openpyxl)가 설치되어 있는지 확인해주세요.")
            st.code("pip install openpyxl", language="bash")
            return

        # 데이터가 없는 경우 처리
        if df is None or len(df) == 0:
            st.warning("⚠️ 분석할 수 있는 데이터가 없습니다.")
            if st.session_state.get('cancelled_count', 0) > 0:
                st.info(f"모든 거래({st.session_state['cancelled_count']}건)가 취소된 거래(해제사유발생일 있음)로 확인되어 제외되었습니다.")
            st.info("다른 파일을 업로드하거나 데이터 구성을 확인해주세요.")
            return
    else:
        # 파일이 업로드되지 않은 경우 초기 화면 표시
        title_placeholder.title("📊 실거래가 분석 대시보드")
        st.info("👈 왼쪽 사이드바에서 'Excel 파일 업로드'를 통해 분석할 파일을 선택해주세요.")

        st.markdown("""
        ### 🚀 시작하기
        1. 왼쪽 사이드바의 **파일 업로드** 섹션을 클릭하여 엽니다.
        2. 국토교통부 실거래가 공개시스템에서 다운로드한 **Excel 파일(.xlsx)**을 업로드하세요.
        3. 업로드가 완료되면 자동으로 대시보드가 생성됩니다.

        #### 지원 파일 유형
        | 유형 | 파일명 예시 |
        |------|-----------|
        | 🏠 아파트 매매 | `서울 아파트(매매)_실거래가_....xlsx` |
        | 🏢 오피스텔 매매 | `서울 오피스텔(매매)_실거래가_....xlsx` |
        | 🏢 오피스텔 전월세 | `서울 오피스텔(전월세)_실거래가_....xlsx` |
        """)

        available_files = [f for f in os.listdir('.') if f.endswith('.xlsx')]
        if available_files:
            st.markdown("---")
            st.markdown("##### 📁 현재 폴더의 데이터 파일 목록")
            for f in available_files:
                st.write(f"- {f}")

        return

    # 전체 데이터 건수 표시
    st.sidebar.metric("📊 전체 데이터", f"{len(df):,} 건")

    # 취소된 거래 건수 표시 (있는 경우)
    if st.session_state.get('cancelled_count', 0) > 0:
        st.sidebar.warning(f"🚫 취소된 거래 {st.session_state['cancelled_count']}건 제외됨")

    # 사이드바 필터
    st.sidebar.markdown("---")
    st.sidebar.markdown("### 🔍 검색 필터")

    # 1. 지역 필터 (접을 수 있게)
    regions = sorted(df['시군구'].unique())
    selected_region = regions  # 기본값: 전체 지역

    with st.sidebar.expander("📍 지역 선택", expanded=False):
        selected_region = st.multiselect("시군구", regions, default=regions, label_visibility="collapsed")

    # 1-1. 전월세 전용: 전월세구분 필터
    selected_rent_types = None
    if property_type == "오피스텔전월세" and '전월세구분' in df.columns:
        rent_types = sorted(df['전월세구분'].dropna().unique())
        with st.sidebar.expander("🏷️ 전월세 구분", expanded=False):
            selected_rent_types = st.multiselect(
                "전월세구분", rent_types, default=rent_types, label_visibility="collapsed"
            )
    
    # 2. 단지(건물)명 검색/필터 (접을 수 있게)
    complex_label = "건물명 검색" if property_type != "아파트매매" else "단지명 검색"
    all_complexes = sorted(df['단지명'].unique())
    selected_complexes = all_complexes  # 기본값: 전체 단지

    with st.sidebar.expander(f"🏢 {complex_label}", expanded=False):
        # 단지명 검색 방식 선택
        search_mode = st.radio(
            "검색 방식",
            ["전체 단지", "단지명 검색", "단지명 선택"],
            help="전체 단지: 모든 단지 표시\n단지명 검색: 키워드로 검색\n단지명 선택: 목록에서 선택",
            label_visibility="collapsed"
        )
        
        if search_mode == "단지명 검색":
            # 검색어 입력
            search_keyword = st.text_input(
                "검색어 입력",
                placeholder="예: 힐스테이트, 래미안",
                help="단지명에 포함된 키워드를 입력하세요",
                label_visibility="visible"
            )
            if search_keyword:
                # 검색어가 포함된 단지명 필터링
                matching_complexes = [c for c in all_complexes if search_keyword.lower() in str(c).lower()]
                if matching_complexes:
                    selected_complexes = st.multiselect(
                        "검색된 단지",
                        matching_complexes,
                        default=matching_complexes,
                        help=f"'{search_keyword}' 검색 결과: {len(matching_complexes)}개",
                        label_visibility="visible"
                    )
                else:
                    st.warning(f"'{search_keyword}'에 해당하는 단지를 찾을 수 없습니다.")
                    selected_complexes = []
            else:
                # 검색어가 없으면 전체 단지
                selected_complexes = all_complexes
        
        elif search_mode == "단지명 선택":
            # 단지명 다중 선택
            selected_complexes = st.multiselect(
                "단지명 선택",
                all_complexes,
                help="분석할 단지를 선택하세요 (복수 선택 가능)",
                label_visibility="visible"
            )
            if not selected_complexes:
                # 선택하지 않으면 전체 단지
                selected_complexes = all_complexes
        else:
            # 전체 단지
            selected_complexes = all_complexes
    
    # 3. 날짜 필터 (접을 수 있게)
    # NaT 또는 빈 데이터 대응
    min_date = df['거래일자'].min()
    max_date = df['거래일자'].max()
    
    if pd.isna(min_date) or pd.isna(max_date):
        st.error("데이터에서 유효한 거래일자를 찾을 수 없습니다.")
        return
        
    date_range = [min_date, max_date]
    
    with st.sidebar.expander("📅 기간 설정", expanded=False):
        date_range = st.date_input("조회 기간", [min_date, max_date], label_visibility="collapsed")
    
    # 4. 전용면적 필터 (접을 수 있게)
    min_area = float(df['전용면적(㎡)'].min()) if not df['전용면적(㎡)'].empty else 0.0
    max_area = float(df['전용면적(㎡)'].max()) if not df['전용면적(㎡)'].empty else 100.0
    
    if pd.isna(min_area) or pd.isna(max_area):
        min_area, max_area = 0.0, 100.0
        
    area_range = (min_area, max_area)
    
    with st.sidebar.expander("📐 전용면적 필터", expanded=False):
        area_range = st.slider(
            "전용면적 범위 선택 (㎡)",
            min_value=min_area,
            max_value=max_area,
            value=(min_area, max_area),
            step=1.0,
            help="분석할 전용면적 범위를 선택하세요"
        )
    
    # 데이터 필터링 적용
    if not selected_region:
        selected_region = regions

    mask = df['시군구'].isin(selected_region)

    # 단지(건물)명 필터 적용
    if selected_complexes and len(selected_complexes) < len(all_complexes):
        mask = mask & (df['단지명'].isin(selected_complexes))

    # 전월세 구분 필터 적용
    if selected_rent_types is not None and len(selected_rent_types) < len(df['전월세구분'].dropna().unique()):
        mask = mask & (df['전월세구분'].isin(selected_rent_types))

    # 날짜 필터 적용
    if len(date_range) == 2:
        mask = mask & (df['거래일자'] >= pd.to_datetime(date_range[0])) & (df['거래일자'] <= pd.to_datetime(date_range[1]))

    # 전용면적 필터 적용
    mask = mask & (df['전용면적(㎡)'] >= area_range[0]) & (df['전용면적(㎡)'] <= area_range[1])
    
    filtered_df = df[mask].copy()
    
    # 필터링된 데이터 정보 표시
    info_text = f"선택된 데이터: 총 {len(filtered_df):,} 건의 거래 내역이 있습니다."
    
    # 선택된 단지 정보 추가
    if selected_complexes and len(selected_complexes) < len(all_complexes):
        if len(selected_complexes) <= 5:
            complexes_text = ", ".join(selected_complexes)
        else:
            complexes_text = f"{', '.join(selected_complexes[:5])} 외 {len(selected_complexes) - 5}개 단지"
        info_text += f"\n\n🏢 선택된 단지: {complexes_text}"
    
    # 전용면적 필터 정보 추가 (기본값이 아닐 경우만)
    if area_range[0] != min_area or area_range[1] != max_area:
        info_text += f"\n\n📐 전용면적: {area_range[0]:.1f}㎡ ~ {area_range[1]:.1f}㎡"
    
    st.info(info_text)
    
    # 탭 구성
    tab0, tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8 = st.tabs([
        "📊 요약 대시보드",
        "📅 기간별 분석", 
        "💰 금액별 분석", 
        "📐 면적별 분석", 
        "🏗️ 입주년도별 분석",
        "🏢 층수별 분석",
        "🗺️ 지역별 비교",
        "🏢 단지별 분석",
        "📈 신고가 추세 분석"
    ])
    
    # --- 0. 요약 대시보드 ---
    with tab0:
        st.subheader("📊 핵심 지표 요약")

        # KPI 카드
        col1, col2, col3, col4 = st.columns(4)

        with col1:
            total_count = len(filtered_df)
            st.metric("총 거래건수", f"{total_count:,} 건")

        with col2:
            avg_price = filtered_df['거래금액(만원)'].mean()
            if property_type == "오피스텔전월세":
                st.metric("평균 보증금", f"{avg_price:,.0f} 만원")
            else:
                st.metric("평균 거래금액", f"{avg_price:,.0f} 만원")

        with col3:
            if property_type == "오피스텔전월세" and '월세금(만원)' in filtered_df.columns:
                avg_monthly = filtered_df['월세금(만원)'].mean()
                st.metric("평균 월세금", f"{avg_monthly:,.0f} 만원")
            else:
                avg_price_per_pyeong = filtered_df['평당가(만원)'].mean()
                st.metric("평균 평당가", f"{avg_price_per_pyeong:,.0f} 만원")

        with col4:
            max_price = filtered_df['거래금액(만원)'].max()
            min_price = filtered_df['거래금액(만원)'].min()
            if property_type == "오피스텔전월세":
                st.metric("보증금 최고/최저", f"{max_price:,.0f} / {min_price:,.0f} 만원")
            else:
                st.metric("최고가 / 최저가", f"{max_price:,.0f} / {min_price:,.0f} 만원")

        # 전월세 전용: 전세/월세 비율
        if property_type == "오피스텔전월세" and '전월세구분' in filtered_df.columns:
            st.markdown("---")
            rent_ratio = filtered_df['전월세구분'].value_counts().reset_index()
            rent_ratio.columns = ['구분', '건수']
            col_r1, col_r2 = st.columns([1, 3])
            with col_r1:
                st.dataframe(rent_ratio, use_container_width=True, hide_index=True)
            with col_r2:
                fig_rent_pie = px.pie(rent_ratio, values='건수', names='구분', title='전세 / 월세 비율')
                st.plotly_chart(fig_rent_pie, use_container_width=True)
        
        st.markdown("---")
        
        # 주요 통계 요약 테이블
        col_sum1, col_sum2 = st.columns(2)
        
        with col_sum1:
            st.markdown("### 지역별 요약 통계")
            region_summary = filtered_df.groupby('시군구').agg({
                '거래금액(만원)': ['count', 'mean'],
                '평당가(만원)': 'mean'
            }).reset_index()
            region_summary.columns = ['시군구', '거래건수', '평균거래금액(만원)', '평균평당가(만원)']
            region_summary = region_summary.sort_values('거래건수', ascending=False)
            region_summary['평균거래금액(만원)'] = region_summary['평균거래금액(만원)'].round(0).astype(int)
            region_summary['평균평당가(만원)'] = region_summary['평균평당가(만원)'].round(0).astype(int)
            st.dataframe(region_summary, use_container_width=True, hide_index=True)
        
        with col_sum2:
            st.markdown("### 평형대별 요약 통계")
            # 평형 구분 함수 재사용
            def get_area_type(x):
                if x < 60: return '소형(59㎡이하)'
                elif x < 85: return '중소형(59~84㎡)'
                elif x < 102: return '중형(85~102㎡)'
                elif x < 135: return '중대형(102~135㎡)'
                else: return '대형(135㎡초과)'
            
            filtered_df['평형구분'] = filtered_df['전용면적(㎡)'].apply(get_area_type)
            area_summary = filtered_df.groupby('평형구분').agg({
                '거래금액(만원)': ['count', 'mean', 'max', 'min'],
                '평당가(만원)': 'mean'
            }).reset_index()
            area_summary.columns = ['평형구분', '거래건수', '평균거래금액(만원)', '최고가(만원)', '최저가(만원)', '평균평당가(만원)']
            order_list = ['소형(59㎡이하)', '중소형(59~84㎡)', '중형(85~102㎡)', '중대형(102~135㎡)', '대형(135㎡초과)']
            existing_categories = [cat for cat in order_list if cat in area_summary['평형구분'].values]
            area_summary['평형구분'] = pd.Categorical(area_summary['평형구분'], categories=existing_categories, ordered=True)
            area_summary = area_summary.sort_values('평형구분')
            area_summary['평균거래금액(만원)'] = area_summary['평균거래금액(만원)'].round(0).astype(int)
            area_summary['최고가(만원)'] = area_summary['최고가(만원)'].round(0).astype(int)
            area_summary['최저가(만원)'] = area_summary['최저가(만원)'].round(0).astype(int)
            area_summary['평균평당가(만원)'] = area_summary['평균평당가(만원)'].round(0).astype(int)
            st.dataframe(area_summary, use_container_width=True, hide_index=True)
        
        st.markdown("---")
        
        # 건축년도별 요약
        st.markdown("### 건축년도별 요약 통계")
        year_summary = filtered_df.groupby('건축년도').agg({
            '거래금액(만원)': ['count', 'mean'],
            '평당가(만원)': 'mean'
        }).reset_index()
        year_summary.columns = ['건축년도', '거래건수', '평균거래금액(만원)', '평균평당가(만원)']
        year_summary = year_summary.sort_values('건축년도', ascending=False)
        year_summary['평균거래금액(만원)'] = year_summary['평균거래금액(만원)'].round(0).astype(int)
        year_summary['평균평당가(만원)'] = year_summary['평균평당가(만원)'].round(0).astype(int)
        st.dataframe(year_summary, use_container_width=True, hide_index=True)
        
        st.markdown("---")
        
        # 최근 거래 TOP 5
        st.markdown("### 최근 거래 TOP 5")
        recent_transactions = filtered_df.nlargest(5, '거래일자')[['거래일자', '시군구', '단지명', '전용면적(㎡)', '층', '거래금액(만원)', '평당가(만원)', '건축년도']].copy()
        recent_transactions['거래일자'] = recent_transactions['거래일자'].dt.strftime('%Y-%m-%d')
        recent_transactions['평당가(만원)'] = recent_transactions['평당가(만원)'].round(0).astype(int)
        st.dataframe(recent_transactions, use_container_width=True, hide_index=True)
    
    # --- 1. 기간별 분석 ---
    with tab1:
        st.subheader("기간별 거래량 및 평균 시세 추이")
        
        # 월별 데이터 집계
        filtered_df['년월'] = filtered_df['거래일자'].dt.to_period('M').astype(str)
        # 년월을 한글 형식으로 변환
        filtered_df['년월_한글'] = filtered_df['년월'].apply(format_yearmonth_korean)
        monthly_stats = filtered_df.groupby('년월').agg({
            '거래금액(만원)': 'mean',
            'NO': 'count'
        }).reset_index()
        monthly_stats.columns = ['년월', '평균거래금액', '거래량']
        # 년월을 한글 형식으로 변환
        monthly_stats['년월_한글'] = monthly_stats['년월'].apply(format_yearmonth_korean)
        
        # 복합 차트 (Bar: 거래량, Line: 금액)
        fig1 = go.Figure()
        
        # 거래량 (막대)
        fig1.add_trace(go.Bar(
            x=monthly_stats['년월_한글'],
            y=monthly_stats['거래량'],
            name='거래량(건)',
            marker_color='lightblue',
            yaxis='y2'
        ))
        
        # 평균거래금액 (선)
        fig1.add_trace(go.Scatter(
            x=monthly_stats['년월_한글'],
            y=monthly_stats['평균거래금액'],
            name='평균거래금액(만원)',
            mode='lines+markers',
            line=dict(color='firebrick', width=3)
        ))
        
        fig1.update_layout(
            title='월별 거래량 및 평균 거래금액 추이',
            xaxis_title='년월',
            yaxis=dict(title='평균 거래금액(만원)'),
            yaxis2=dict(title='거래량(건)', overlaying='y', side='right'),
            legend=dict(x=0, y=1.1, orientation='h'),
            hovermode="x unified"
        )
        # y축 금액 레이블을 한글로 변환
        max_price = monthly_stats['평균거래금액'].max()
        fig1 = format_price_axis(fig1, axis='y', max_value=max_price)
        st.plotly_chart(fig1, use_container_width=True)
        
        # 주간별 데이터 집계
        st.markdown("---")
        st.subheader("주간별 거래량 추이")
        
        # 주간 데이터 집계 (주 시작일 기준)
        filtered_df['주'] = filtered_df['거래일자'].dt.to_period('W').astype(str)
        weekly_stats = filtered_df.groupby('주').agg({
            'NO': 'count',
            '거래금액(만원)': 'mean'
        }).reset_index()
        weekly_stats.columns = ['주', '거래량', '평균거래금액']
        
        # 주간별 거래량 차트
        fig_weekly = go.Figure()
        
        # 거래량 (막대)
        fig_weekly.add_trace(go.Bar(
            x=weekly_stats['주'],
            y=weekly_stats['거래량'],
            name='주간 거래량(건)',
            marker_color='steelblue',
            text=weekly_stats['거래량'],
            textposition='outside'
        ))
        
        fig_weekly.update_layout(
            title='주간별 거래량 추이',
            xaxis_title='주 (Year-Week)',
            yaxis_title='거래량(건)',
            hovermode="x unified",
            xaxis=dict(tickangle=-45)
        )
        st.plotly_chart(fig_weekly, use_container_width=True)
        
        # 주간별 평균 거래금액도 함께 표시 (선택사항)
        fig_weekly_price = px.line(
            weekly_stats,
            x='주',
            y='평균거래금액',
            markers=True,
            title='주간별 평균 거래금액 추이',
            labels={'평균거래금액': '평균 거래금액(만원)', '주': '주 (Year-Week)'}
        )
        fig_weekly_price.update_layout(
            xaxis=dict(tickangle=-45),
            hovermode="x unified"
        )
        # y축 금액 레이블을 한글로 변환
        max_price = weekly_stats['평균거래금액'].max()
        fig_weekly_price = format_price_axis(fig_weekly_price, axis='y', max_value=max_price)
        st.plotly_chart(fig_weekly_price, use_container_width=True)
        
        # 가격 추세 분석
        st.markdown("---")
        st.subheader("가격 추세 분석")
        
        # 월별 가격 변화율 계산
        monthly_stats_sorted = monthly_stats.sort_values('년월').copy()
        monthly_stats_sorted['전월대비변화율'] = monthly_stats_sorted['평균거래금액'].pct_change() * 100
        
        # 이동평균 계산 (3개월, 6개월)
        monthly_stats_sorted['이동평균_3개월'] = monthly_stats_sorted['평균거래금액'].rolling(window=3, min_periods=1).mean()
        monthly_stats_sorted['이동평균_6개월'] = monthly_stats_sorted['평균거래금액'].rolling(window=6, min_periods=1).mean()
        # 년월을 한글 형식으로 변환
        monthly_stats_sorted['년월_한글'] = monthly_stats_sorted['년월'].apply(format_yearmonth_korean)
        
        # 추세 차트 (이동평균선 포함)
        fig_trend = go.Figure()
        
        # 실제 평균 거래금액
        fig_trend.add_trace(go.Scatter(
            x=monthly_stats_sorted['년월_한글'],
            y=monthly_stats_sorted['평균거래금액'],
            name='월평균 거래금액',
            mode='lines+markers',
            line=dict(color='firebrick', width=2),
            marker=dict(size=8)
        ))
        
        # 3개월 이동평균
        fig_trend.add_trace(go.Scatter(
            x=monthly_stats_sorted['년월_한글'],
            y=monthly_stats_sorted['이동평균_3개월'],
            name='3개월 이동평균',
            mode='lines',
            line=dict(color='blue', width=2, dash='dash')
        ))
        
        # 6개월 이동평균
        fig_trend.add_trace(go.Scatter(
            x=monthly_stats_sorted['년월_한글'],
            y=monthly_stats_sorted['이동평균_6개월'],
            name='6개월 이동평균',
            mode='lines',
            line=dict(color='green', width=2, dash='dot')
        ))
        
        fig_trend.update_layout(
            title='가격 추세 분석 (이동평균선 포함)',
            xaxis_title='년월',
            yaxis_title='평균 거래금액(만원)',
            hovermode="x unified",
            legend=dict(x=0, y=1.1, orientation='h')
        )
        # y축 금액 레이블을 한글로 변환
        max_price = monthly_stats_sorted['평균거래금액'].max()
        fig_trend = format_price_axis(fig_trend, axis='y', max_value=max_price)
        st.plotly_chart(fig_trend, use_container_width=True)
        
        # 전월 대비 변화율 차트
        col_trend1, col_trend2 = st.columns(2)
        
        with col_trend1:
            # 변화율 막대 차트 (상승/하락 색상 구분)
            monthly_stats_sorted['변화율_색상'] = monthly_stats_sorted['전월대비변화율'].apply(
                lambda x: 'green' if x > 0 else 'red' if x < 0 else 'gray'
            )
            
            fig_change = go.Figure()
            fig_change.add_trace(go.Bar(
                x=monthly_stats_sorted['년월_한글'],
                y=monthly_stats_sorted['전월대비변화율'],
                name='전월 대비 변화율(%)',
                marker_color=monthly_stats_sorted['전월대비변화율'].apply(
                    lambda x: 'rgba(34, 139, 34, 0.6)' if x > 0 else 'rgba(220, 20, 60, 0.6)' if x < 0 else 'rgba(128, 128, 128, 0.6)'
                ),
                text=[f"{x:.1f}%" if pd.notna(x) else "-" for x in monthly_stats_sorted['전월대비변화율']],
                textposition='outside'
            ))
            
            fig_change.update_layout(
                title='전월 대비 가격 변화율 (%)',
                xaxis_title='년월',
                yaxis_title='변화율 (%)',
                hovermode="x unified"
            )
            fig_change.add_hline(y=0, line_dash="dash", line_color="black", opacity=0.3)
            st.plotly_chart(fig_change, use_container_width=True)
        
        with col_trend2:
            # 변화율 통계 테이블
            st.markdown("#### 전월 대비 변화율 통계")
            change_stats = monthly_stats_sorted[['년월_한글', '평균거래금액', '전월대비변화율']].copy()
            change_stats = change_stats[change_stats['전월대비변화율'].notna()]
            change_stats['평균거래금액'] = change_stats['평균거래금액'].round(0).astype(int)
            change_stats['전월대비변화율'] = change_stats['전월대비변화율'].round(2)
            change_stats.columns = ['년월', '평균거래금액(만원)', '변화율(%)']
            st.dataframe(change_stats, use_container_width=True, hide_index=True)
            
            # 전체 추세 요약
            if len(change_stats) > 0:
                avg_change = change_stats['변화율(%)'].mean()
                st.metric("평균 월간 변화율", f"{avg_change:.2f}%")
    
    # --- 2. 금액별 분석 ---
    with tab2:
        st.subheader("거래 금액대별 분포")
        
        col1, col2 = st.columns(2)
        
        with col1:
            # 히스토그램
            fig2 = px.histogram(
                filtered_df, 
                x="거래금액(만원)", 
                nbins=30, 
                title="거래 금액 분포 (히스토그램)",
                color_discrete_sequence=['#636EFA']
            )
            fig2.update_layout(xaxis_title="거래금액(만원)", yaxis_title="건수")
            # x축 금액 레이블을 한글로 변환
            max_price = filtered_df['거래금액(만원)'].max()
            fig2 = format_price_axis(fig2, axis='x', max_value=max_price)
            st.plotly_chart(fig2, use_container_width=True)
            
        with col2:
            # Box Plot (이상치 확인용)
            fig3 = px.box(
                filtered_df, 
                y="거래금액(만원)", 
                title="거래 금액 범위 및 이상치 확인",
                points="all"
            )
            # y축 금액 레이블을 한글로 변환
            max_price = filtered_df['거래금액(만원)'].max()
            fig3 = format_price_axis(fig3, axis='y', max_value=max_price)
            st.plotly_chart(fig3, use_container_width=True)
        
        # 금액 구간별 통계
        bins = [0, 50000, 100000, 150000, 200000, 300000, 9999999]
        labels = ['5억 미만', '5억~10억', '10억~15억', '15억~20억', '20억~30억', '30억 이상']
        filtered_df['금액구간'] = pd.cut(filtered_df['거래금액(만원)'], bins=bins, labels=labels)
        
        price_group = filtered_df['금액구간'].value_counts().reset_index()
        price_group.columns = ['금액구간', '거래건수']
        
        fig_pie = px.pie(price_group, values='거래건수', names='금액구간', title='금액대별 거래 비중')
        st.plotly_chart(fig_pie, use_container_width=True)
    
    # --- 3. 면적별 분석 ---
    with tab3:
        st.subheader("전용면적 및 평수별 가격 분석")
        
        # 산점도 (면적 vs 가격)
        fig4 = px.scatter(
            filtered_df, 
            x="전용면적(㎡)", 
            y="거래금액(만원)", 
            color="건축년도",
            size="평수",
            hover_data=['단지명', '층'],
            title="전용면적 대 거래금액 산점도 (색상: 건축년도)",
            color_continuous_scale=px.colors.sequential.Viridis
        )
        # y축 금액 레이블을 한글로 변환
        max_price = filtered_df['거래금액(만원)'].max()
        fig4 = format_price_axis(fig4, axis='y', max_value=max_price)
        st.plotly_chart(fig4, use_container_width=True)
        
        # 평형대 그룹화 분석
        # 대략적인 평형 구분 (소형, 중소형, 중형, 대형)
        def get_area_type(x):
            if x < 60: return '소형(59㎡이하)'
            elif x < 85: return '중소형(59~84㎡)'
            elif x < 102: return '중형(85~102㎡)'
            elif x < 135: return '중대형(102~135㎡)'
            else: return '대형(135㎡초과)'
            
        filtered_df['평형구분'] = filtered_df['전용면적(㎡)'].apply(get_area_type)
        
        area_group = filtered_df.groupby('평형구분').agg({
            '거래금액(만원)': 'mean', 
            '평당가(만원)': 'mean',
            'NO': 'count'
        }).reset_index()
        
        # 순서 정렬
        order_list = ['소형(59㎡이하)', '중소형(59~84㎡)', '중형(85~102㎡)', '중대형(102~135㎡)', '대형(135㎡초과)']
        # 데이터에 존재하는 카테고리만 순서 목록에 포함
        existing_categories = [cat for cat in order_list if cat in area_group['평형구분'].values]
        area_group['평형구분'] = pd.Categorical(area_group['평형구분'], categories=existing_categories, ordered=True)
        area_group = area_group.sort_values('평형구분')
        
        fig5 = px.bar(
            area_group, 
            x='평형구분', 
            y='평당가(만원)', 
            color='평당가(만원)',
            text_auto='.0f',
            title='평형대별 평균 평당가(만원)',
            color_continuous_scale='Blues'
        )
        # y축 금액 레이블을 한글로 변환 (평당가는 보통 작은 값이므로 별도 처리)
        max_pyeong = area_group['평당가(만원)'].max()
        fig5 = format_price_axis(fig5, axis='y', max_value=max_pyeong)
        st.plotly_chart(fig5, use_container_width=True)
    
    # --- 4. 입주년도(건축년도)별 분석 ---
    with tab4:
        st.subheader("건축년도(연식)에 따른 가격 흐름")
        
        # 건축년도별 평균 가격
        year_stats = filtered_df.groupby('건축년도')['거래금액(만원)'].mean().reset_index()
        
        fig6 = px.line(
            year_stats, 
            x='건축년도', 
            y='거래금액(만원)', 
            markers=True,
            title='건축년도별 평균 거래금액 추이'
        )
        # y축 금액 레이블을 한글로 변환
        max_price = year_stats['거래금액(만원)'].max()
        fig6 = format_price_axis(fig6, axis='y', max_value=max_price)
        st.plotly_chart(fig6, use_container_width=True)
        
        # 구축 vs 신축 비교 (예: 2015년 기준)
        filtered_df['건물유형'] = filtered_df['건축년도'].apply(lambda x: '신축(10년이내)' if x >= 2015 else '구축')
        
        fig7 = px.box(
            filtered_df,
            x='건물유형',
            y='평당가(만원)',
            color='건물유형',
            title='신축 vs 구축 평당가 비교 (2015년 기준)'
        )
        # y축 금액 레이블을 한글로 변환
        max_pyeong = filtered_df['평당가(만원)'].max()
        fig7 = format_price_axis(fig7, axis='y', max_value=max_pyeong)
        st.plotly_chart(fig7, use_container_width=True)
    
    # --- 5. 층수별 분석 ---
    with tab5:
        st.subheader("층수에 따른 가격 분석")
        
        # 층수 구간 분류 함수
        def get_floor_category(floor):
            if pd.isna(floor):
                return '정보없음'
            floor_num = int(floor) if isinstance(floor, (int, float)) else int(str(floor).replace('층', '').strip())
            if floor_num <= 5:
                return '저층(1~5층)'
            elif floor_num <= 15:
                return '중층(6~15층)'
            elif floor_num <= 30:
                return '고층(16~30층)'
            else:
                return '초고층(31층 이상)'
        
        filtered_df['층수구간'] = filtered_df['층'].apply(get_floor_category)
        
        # 층수 구간별 평균 가격
        col_floor1, col_floor2 = st.columns(2)
        
        with col_floor1:
            floor_group = filtered_df.groupby('층수구간').agg({
                '거래금액(만원)': 'mean',
                '평당가(만원)': 'mean',
                'NO': 'count'
            }).reset_index()
            floor_group.columns = ['층수구간', '평균거래금액', '평균평당가', '거래건수']
            
            # 순서 정렬
            floor_order = ['저층(1~5층)', '중층(6~15층)', '고층(16~30층)', '초고층(31층 이상)', '정보없음']
            existing_floor_cats = [cat for cat in floor_order if cat in floor_group['층수구간'].values]
            floor_group['층수구간'] = pd.Categorical(floor_group['층수구간'], categories=existing_floor_cats, ordered=True)
            floor_group = floor_group.sort_values('층수구간')
            
            fig_floor_bar = px.bar(
                floor_group,
                x='층수구간',
                y='평균평당가',
                color='평균평당가',
                text_auto='.0f',
                title='층수 구간별 평균 평당가',
                color_continuous_scale='Oranges'
            )
            # y축 금액 레이블을 한글로 변환
            max_pyeong = floor_group['평균평당가'].max()
            fig_floor_bar = format_price_axis(fig_floor_bar, axis='y', max_value=max_pyeong)
            st.plotly_chart(fig_floor_bar, use_container_width=True)
        
        with col_floor2:
            # 층수별 평당가 박스플롯
            fig_floor_box = px.box(
                filtered_df,
                x='층수구간',
                y='평당가(만원)',
                color='층수구간',
                title='층수 구간별 평당가 분포',
                category_orders={'층수구간': ['저층(1~5층)', '중층(6~15층)', '고층(16~30층)', '초고층(31층 이상)', '정보없음']}
            )
            # y축 금액 레이블을 한글로 변환
            max_pyeong = filtered_df['평당가(만원)'].max()
            fig_floor_box = format_price_axis(fig_floor_box, axis='y', max_value=max_pyeong)
            st.plotly_chart(fig_floor_box, use_container_width=True)
        
        # 층수 vs 가격 산점도
        st.markdown("---")
        st.subheader("층수와 가격의 관계")
        
        # 층수를 숫자로 변환
        def extract_floor_num(floor):
            if pd.isna(floor):
                return None
            try:
                if isinstance(floor, (int, float)):
                    return int(floor)
                return int(str(floor).replace('층', '').strip())
            except:
                return None
        
        filtered_df['층수_숫자'] = filtered_df['층'].apply(extract_floor_num)
        floor_scatter_df = filtered_df[filtered_df['층수_숫자'].notna()].copy()
        
        if len(floor_scatter_df) > 0:
            fig_floor_scatter = px.scatter(
                floor_scatter_df,
                x='층수_숫자',
                y='거래금액(만원)',
                color='평당가(만원)',
                size='전용면적(㎡)',
                hover_data=['단지명', '건축년도'],
                title='층수 vs 거래금액 산점도',
                labels={'층수_숫자': '층수', '거래금액(만원)': '거래금액(만원)'},
                color_continuous_scale=px.colors.sequential.Viridis
            )
            # y축 금액 레이블을 한글로 변환
            max_price = floor_scatter_df['거래금액(만원)'].max()
            fig_floor_scatter = format_price_axis(fig_floor_scatter, axis='y', max_value=max_price)
            st.plotly_chart(fig_floor_scatter, use_container_width=True)
        
        # 고층 프리미엄 분석
        st.markdown("---")
        st.subheader("고층 프리미엄 분석")
        
        col_premium1, col_premium2 = st.columns(2)
        
        with col_premium1:
            # 최상층 vs 평균층 가격 비교
            if len(floor_scatter_df) > 0:
                max_floor = floor_scatter_df['층수_숫자'].max()
                avg_floor = floor_scatter_df['층수_숫자'].mean()
                
                # 최상층 거래 (상위 10% 층수)
                top_floor_threshold = floor_scatter_df['층수_숫자'].quantile(0.9)
                top_floor_df = floor_scatter_df[floor_scatter_df['층수_숫자'] >= top_floor_threshold]
                avg_floor_df = floor_scatter_df[floor_scatter_df['층수_숫자'] < top_floor_threshold]
                
                if len(top_floor_df) > 0 and len(avg_floor_df) > 0:
                    top_floor_avg_price = top_floor_df['평당가(만원)'].mean()
                    avg_floor_avg_price = avg_floor_df['평당가(만원)'].mean()
                    premium_rate = ((top_floor_avg_price - avg_floor_avg_price) / avg_floor_avg_price) * 100
                    
                    st.metric("최상층 평균 평당가", f"{top_floor_avg_price:,.0f} 만원")
                    st.metric("일반층 평균 평당가", f"{avg_floor_avg_price:,.0f} 만원")
                    st.metric("고층 프리미엄", f"{premium_rate:.2f}%", 
                             delta=f"{top_floor_avg_price - avg_floor_avg_price:,.0f} 만원")
        
        with col_premium2:
            # 층수 구간별 통계 테이블
            st.markdown("#### 층수 구간별 상세 통계")
            floor_stats = filtered_df.groupby('층수구간').agg({
                '거래금액(만원)': ['count', 'mean', 'min', 'max'],
                '평당가(만원)': 'mean'
            }).reset_index()
            floor_stats.columns = ['층수구간', '거래건수', '평균거래금액', '최저가', '최고가', '평균평당가']
            floor_stats = floor_stats.sort_values('층수구간', key=lambda x: x.map({
                '저층(1~5층)': 1, '중층(6~15층)': 2, '고층(16~30층)': 3, 
                '초고층(31층 이상)': 4, '정보없음': 5
            }))
            floor_stats['평균거래금액'] = floor_stats['평균거래금액'].round(0).astype(int)
            floor_stats['평균평당가'] = floor_stats['평균평당가'].round(0).astype(int)
            floor_stats['최저가'] = floor_stats['최저가'].round(0).astype(int)
            floor_stats['최고가'] = floor_stats['최고가'].round(0).astype(int)
            st.dataframe(floor_stats, use_container_width=True, hide_index=True)
    
    # --- 6. 지역별 비교 분석 ---
    with tab6:
        st.subheader("지역별 비교 분석")
        
        # 지역별 평균 거래금액 비교
        region_comparison = filtered_df.groupby('시군구').agg({
            '거래금액(만원)': ['mean', 'count'],
            '평당가(만원)': 'mean'
        }).reset_index()
        region_comparison.columns = ['시군구', '평균거래금액', '거래건수', '평균평당가']
        region_comparison = region_comparison.sort_values('평균거래금액', ascending=False)
        
        col_region1, col_region2 = st.columns(2)
        
        with col_region1:
            # 지역별 평균 거래금액 막대 차트
            fig_region_price = px.bar(
                region_comparison,
                x='시군구',
                y='평균거래금액',
                color='평균거래금액',
                text_auto='.0f',
                title='지역별 평균 거래금액 비교',
                color_continuous_scale='Blues',
                labels={'평균거래금액': '평균 거래금액(만원)'}
            )
            fig_region_price.update_layout(xaxis_tickangle=-45)
            # y축 금액 레이블을 한글로 변환
            max_price = region_comparison['평균거래금액'].max()
            fig_region_price = format_price_axis(fig_region_price, axis='y', max_value=max_price)
            st.plotly_chart(fig_region_price, use_container_width=True)
        
        with col_region2:
            # 지역별 평균 평당가 막대 차트
            fig_region_pyeong = px.bar(
                region_comparison,
                x='시군구',
                y='평균평당가',
                color='평균평당가',
                text_auto='.0f',
                title='지역별 평균 평당가 비교',
                color_continuous_scale='Greens',
                labels={'평균평당가': '평균 평당가(만원)'}
            )
            fig_region_pyeong.update_layout(xaxis_tickangle=-45)
            # y축 금액 레이블을 한글로 변환
            max_pyeong = region_comparison['평균평당가'].max()
            fig_region_pyeong = format_price_axis(fig_region_pyeong, axis='y', max_value=max_pyeong)
            st.plotly_chart(fig_region_pyeong, use_container_width=True)
        
        # 지역별 거래량 비교
        st.markdown("---")
        fig_region_vol = px.bar(
            region_comparison,
            x='시군구',
            y='거래건수',
            color='거래건수',
            text_auto='.0f',
            title='지역별 거래량 비교',
            color_continuous_scale='Reds',
            labels={'거래건수': '거래건수(건)'}
        )
        fig_region_vol.update_layout(xaxis_tickangle=-45)
        st.plotly_chart(fig_region_vol, use_container_width=True)
        
        # 지역별 통계 요약 테이블
        st.markdown("---")
        st.subheader("지역별 상세 통계")
        region_comparison['평균거래금액'] = region_comparison['평균거래금액'].round(0).astype(int)
        region_comparison['평균평당가'] = region_comparison['평균평당가'].round(0).astype(int)
        region_comparison.columns = ['시군구', '평균거래금액(만원)', '거래건수(건)', '평균평당가(만원)']
        st.dataframe(region_comparison, use_container_width=True, hide_index=True)
    
    # --- 7. 단지별 분석 ---
    with tab7:
        building_label = "건물" if property_type != "아파트매매" else "단지"
        st.subheader(f"{building_label}별 거래 순위")
        
        col_apt1, col_apt2 = st.columns(2)
        
        with col_apt1:
            st.markdown("**🏆 거래량 상위 10개 단지**")
            top_vol_apt = filtered_df['단지명'].value_counts().head(10).reset_index()
            top_vol_apt.columns = ['단지명', '거래건수']
            
            fig8 = px.bar(
                top_vol_apt, 
                x='거래건수', 
                y='단지명', 
                orientation='h',
                title='거래량 TOP 10 단지',
                color='거래건수'
            )
            fig8.update_layout(yaxis={'categoryorder':'total ascending'})
            st.plotly_chart(fig8, use_container_width=True)
            
        with col_apt2:
            st.markdown("**💰 평균 거래가 상위 10개 단지**")
            top_price_apt = filtered_df.groupby('단지명')['거래금액(만원)'].mean().sort_values(ascending=False).head(10).reset_index()
            
            fig9 = px.bar(
                top_price_apt, 
                x='거래금액(만원)', 
                y='단지명', 
                orientation='h',
                title='평균 거래금액 TOP 10 단지',
                color='거래금액(만원)',
                color_continuous_scale='Reds'
            )
            fig9.update_layout(yaxis={'categoryorder':'total ascending'})
            # x축 금액 레이블을 한글로 변환 (가로 막대이므로 x축)
            max_price = top_price_apt['거래금액(만원)'].max()
            fig9 = format_price_axis(fig9, axis='x', max_value=max_price)
            st.plotly_chart(fig9, use_container_width=True)
        
        # 평당가 상위 10개 단지
        st.markdown("---")
        st.markdown("**📊 평당가 상위 10개 단지**")
        top_pyeong_apt = filtered_df.groupby('단지명')['평당가(만원)'].mean().sort_values(ascending=False).head(10).reset_index()
        top_pyeong_apt.columns = ['단지명', '평당가(만원)']
        
        fig10 = px.bar(
            top_pyeong_apt,
            x='평당가(만원)',
            y='단지명',
            orientation='h',
            title='평당가 TOP 10 단지',
            color='평당가(만원)',
            color_continuous_scale='Greens'
        )
        fig10.update_layout(yaxis={'categoryorder':'total ascending'})
        # x축 금액 레이블을 한글로 변환
        max_pyeong = top_pyeong_apt['평당가(만원)'].max()
        fig10 = format_price_axis(fig10, axis='x', max_value=max_pyeong)
        st.plotly_chart(fig10, use_container_width=True)
        
        # 단지별 가격 범위 비교 (최고가/최저가)
        st.markdown("---")
        st.markdown("**📈 단지별 가격 범위 비교 (최고가/최저가)**")
        
        # 거래량 상위 10개 단지 선택
        top_10_complexes = filtered_df['단지명'].value_counts().head(10).index.tolist()
        price_range_df = filtered_df[filtered_df['단지명'].isin(top_10_complexes)].copy()
        
        # 각 단지별 최고가, 최저가, 평균가 계산
        price_stats = price_range_df.groupby('단지명')['거래금액(만원)'].agg(['min', 'max', 'mean']).reset_index()
        price_stats.columns = ['단지명', '최저가', '최고가', '평균가']
        price_stats = price_stats.sort_values('평균가', ascending=False)
        
        # 범위 막대 차트 생성 (최저가부터 최고가까지의 범위와 평균가 표시)
        fig11 = go.Figure()
        
        # 최저가부터 최고가까지의 범위를 표시하는 막대
        fig11.add_trace(go.Bar(
            name='가격 범위',
            x=price_stats['단지명'],
            y=price_stats['최고가'] - price_stats['최저가'],  # 범위 길이
            base=price_stats['최저가'],  # 최저가부터 시작
            marker=dict(
                color='lightblue',
                line=dict(color='blue', width=1)
            ),
            hovertemplate='<b>%{x}</b><br>' +
                         '최저가: %{base:,.0f}만원<br>' +
                         '최고가: %{customdata:,.0f}만원<br>' +
                         '범위: %{y:,.0f}만원<extra></extra>',
            customdata=price_stats['최고가']
        ))
        
        # 평균가 마커 추가
        fig11.add_trace(go.Scatter(
            x=price_stats['단지명'],
            y=price_stats['평균가'],
            mode='markers',
            marker=dict(
                symbol='diamond',
                size=12,
                color='red',
                line=dict(color='darkred', width=2)
            ),
            name='평균가',
            hovertemplate='<b>%{x}</b><br>평균가: %{y:,.0f}만원<extra></extra>'
        ))
        
        fig11.update_layout(
            title='단지별 가격 범위 비교 (상위 10개 단지)',
            xaxis_title='단지명',
            yaxis_title='거래금액(만원)',
            xaxis=dict(tickangle=-45),
            hovermode='closest',
            height=600,
            barmode='overlay'
        )
        
        # y축 금액 레이블을 한글로 변환
        max_price_range = price_stats['최고가'].max()
        fig11 = format_price_axis(fig11, axis='y', max_value=max_price_range)
        st.plotly_chart(fig11, use_container_width=True)
        
        st.markdown("### 📋 전체 데이터 조회")
        # 표시용 데이터프레임 생성 (정렬 후 계약년월을 한글 형식으로 변환)
        display_df = filtered_df[['시군구', '단지명', '전용면적(㎡)', '계약년월', '계약일', '거래금액(만원)', '층', '건축년도']].copy()
        # 먼저 정렬 (원본 숫자 형식으로)
        display_df = display_df.sort_values(by=['계약년월', '계약일'], ascending=False)
        # 표시용으로 계약년월 변환
        display_df['계약년월'] = display_df['계약년월'].apply(format_contract_yearmonth)
        st.dataframe(display_df, use_container_width=True, hide_index=True)
    
    # --- 8. 신고가 추세 분석 ---
    with tab8:
        st.subheader("📈 신고가 추세 분석")
        st.markdown("과거 거래가와 현재 거래가를 비교하여 가격 상승 추세를 분석합니다.")
        
        # 비교 기준 설정
        col_setting1, col_setting2 = st.columns(2)
        
        with col_setting1:
            comparison_period = st.selectbox(
                "비교 기간",
                ["3개월 전", "6개월 전", "1년 전"],
                help="현재 거래가와 비교할 과거 기간을 선택하세요"
            )
        
        with col_setting2:
            comparison_criteria = st.selectbox(
                "비교 조건",
                ["같은 단지", "같은 단지 + 면적대", "같은 단지 + 면적대 + 층수대"],
                help="비교할 조건을 선택하세요"
            )
        
        # 비교 기간을 숫자로 변환
        period_months = {"3개월 전": 3, "6개월 전": 6, "1년 전": 12}[comparison_period]
        
        # 현재 날짜 기준으로 과거 기간 계산
        current_date = filtered_df['거래일자'].max()
        past_date = current_date - pd.DateOffset(months=period_months)
        
        # 현재 기간과 과거 기간 데이터 분리
        current_period_df = filtered_df[filtered_df['거래일자'] > past_date].copy()
        past_period_df = filtered_df[filtered_df['거래일자'] <= past_date].copy()
        
        if len(past_period_df) == 0:
            st.warning(f"{comparison_period} 이전 데이터가 없어 분석할 수 없습니다.")
        else:
            st.info(f"현재 기간: {len(current_period_df):,}건 | 과거 기간: {len(past_period_df):,}건")
            
            # 비교 조건에 따른 그룹화 키 생성
            def get_group_key(row, criteria):
                """비교 조건에 따라 그룹화 키 생성"""
                if criteria == "같은 단지":
                    return row['단지명']
                elif criteria == "같은 단지 + 면적대":
                    # 면적대 구분
                    area = row['전용면적(㎡)']
                    if area < 60:
                        area_type = '소형'
                    elif area < 85:
                        area_type = '중소형'
                    elif area < 102:
                        area_type = '중형'
                    elif area < 135:
                        area_type = '중대형'
                    else:
                        area_type = '대형'
                    return f"{row['단지명']}_{area_type}"
                else:  # 같은 단지 + 면적대 + 층수대
                    # 면적대 구분
                    area = row['전용면적(㎡)']
                    if area < 60:
                        area_type = '소형'
                    elif area < 85:
                        area_type = '중소형'
                    elif area < 102:
                        area_type = '중형'
                    elif area < 135:
                        area_type = '중대형'
                    else:
                        area_type = '대형'
                    # 층수대 구분
                    try:
                        floor = int(str(row['층']).replace('층', '').strip()) if pd.notna(row['층']) else 0
                        if floor <= 5:
                            floor_type = '저층'
                        elif floor <= 15:
                            floor_type = '중층'
                        elif floor <= 30:
                            floor_type = '고층'
                        else:
                            floor_type = '초고층'
                    except:
                        floor_type = '기타'
                    return f"{row['단지명']}_{area_type}_{floor_type}"
            
            # 비교 조건에 따라 그룹화 키 추가
            current_period_df['그룹키'] = current_period_df.apply(lambda x: get_group_key(x, comparison_criteria), axis=1)
            past_period_df['그룹키'] = past_period_df.apply(lambda x: get_group_key(x, comparison_criteria), axis=1)
            
            # 1. 단지별 가격 상승 추세 분석
            st.markdown("---")
            st.subheader(f"가격 상승 추세 분석 ({comparison_criteria})")
            
            # 그룹별 평균 가격 계산
            current_avg = current_period_df.groupby('그룹키')['거래금액(만원)'].mean().reset_index()
            current_avg.columns = ['그룹키', '현재평균가']
            
            past_avg = past_period_df.groupby('그룹키')['거래금액(만원)'].mean().reset_index()
            past_avg.columns = ['그룹키', '과거평균가']
            
            # 병합하여 상승률 계산
            price_comparison = current_avg.merge(past_avg, on='그룹키', how='inner')
            price_comparison['상승률(%)'] = ((price_comparison['현재평균가'] - price_comparison['과거평균가']) / price_comparison['과거평균가']) * 100
            price_comparison['상승금액'] = price_comparison['현재평균가'] - price_comparison['과거평균가']
            
            # 그룹키에서 단지명 추출 (표시용)
            price_comparison['단지명'] = price_comparison['그룹키'].str.split('_').str[0]
            
            # 상승률이 높은 단지 TOP 10
            top_rising = price_comparison.nlargest(10, '상승률(%)')
            
            col_rising1, col_rising2 = st.columns(2)
            
            with col_rising1:
                st.markdown("**📈 상승률 TOP 10 단지**")
                fig_rising = px.bar(
                    top_rising,
                    x='상승률(%)',
                    y='단지명',
                    orientation='h',
                    title=f'{comparison_period} 대비 가격 상승률 TOP 10',
                    color='상승률(%)',
                    color_continuous_scale='Reds',
                    text_auto='.1f'
                )
                fig_rising.update_layout(yaxis={'categoryorder':'total ascending'})
                st.plotly_chart(fig_rising, use_container_width=True)
            
            with col_rising2:
                st.markdown("**💰 상승금액 TOP 10 단지**")
                top_amount_rising = price_comparison.nlargest(10, '상승금액')
                fig_amount = px.bar(
                    top_amount_rising,
                    x='상승금액',
                    y='단지명',
                    orientation='h',
                    title=f'{comparison_period} 대비 가격 상승금액 TOP 10',
                    color='상승금액',
                    color_continuous_scale='Oranges',
                    text_auto='.0f'
                )
                fig_amount.update_layout(yaxis={'categoryorder':'total ascending'})
                # x축 금액 레이블을 한글로 변환
                max_amount = top_amount_rising['상승금액'].max()
                fig_amount = format_price_axis(fig_amount, axis='x', max_value=max_amount)
                st.plotly_chart(fig_amount, use_container_width=True)
            
            # 단지별 상세 통계 테이블
            st.markdown("---")
            st.subheader("단지별 가격 변화 상세 통계")
            comparison_display = price_comparison[['단지명', '과거평균가', '현재평균가', '상승금액', '상승률(%)']].copy()
            comparison_display = comparison_display.sort_values('상승률(%)', ascending=False)
            comparison_display['과거평균가'] = comparison_display['과거평균가'].round(0).astype(int)
            comparison_display['현재평균가'] = comparison_display['현재평균가'].round(0).astype(int)
            comparison_display['상승금액'] = comparison_display['상승금액'].round(0).astype(int)
            comparison_display['상승률(%)'] = comparison_display['상승률(%)'].round(2)
            comparison_display.columns = ['단지명', f'{comparison_period} 평균가(만원)', '현재 평균가(만원)', '상승금액(만원)', '상승률(%)']
            st.dataframe(comparison_display, use_container_width=True, hide_index=True)
            
            # 2. 시간에 따른 가격 상승률 추이
            st.markdown("---")
            st.subheader("시간에 따른 가격 상승률 추이")
            
            # 분석 단위 선택
            analysis_unit = st.radio("분석 단위", ["월별", "분기별"], horizontal=True)
            
            if analysis_unit == "월별":
                # 월별 평균 가격 계산
                current_period_df['년월'] = current_period_df['거래일자'].dt.to_period('M').astype(str)
                past_period_df['년월'] = past_period_df['거래일자'].dt.to_period('M').astype(str)
                
                monthly_current = current_period_df.groupby('년월')['거래금액(만원)'].mean().reset_index()
                monthly_current.columns = ['기간', '평균가']
                monthly_current['기간_한글'] = monthly_current['기간'].apply(format_yearmonth_korean)
                
                monthly_past = past_period_df.groupby('년월')['거래금액(만원)'].mean().reset_index()
                monthly_past.columns = ['기간', '평균가']
                monthly_past['기간_한글'] = monthly_past['기간'].apply(format_yearmonth_korean)
                
                period_data = monthly_current.copy()
                period_label = '년월'
            else:
                # 분기별 평균 가격 계산
                current_period_df['분기'] = current_period_df['거래일자'].dt.to_period('Q').astype(str)
                past_period_df['분기'] = past_period_df['거래일자'].dt.to_period('Q').astype(str)
                
                quarterly_current = current_period_df.groupby('분기')['거래금액(만원)'].mean().reset_index()
                quarterly_current.columns = ['기간', '평균가']
                quarterly_current['기간_한글'] = quarterly_current['기간'].apply(lambda x: f"{x[:4]}년 {int(x[-1])}분기")
                
                quarterly_past = past_period_df.groupby('분기')['거래금액(만원)'].mean().reset_index()
                quarterly_past.columns = ['기간', '평균가']
                quarterly_past['기간_한글'] = quarterly_past['기간'].apply(lambda x: f"{x[:4]}년 {int(x[-1])}분기")
                
                period_data = quarterly_current.copy()
                period_label = '분기'
            
            # 과거 기간의 평균 가격 (기준선)
            past_avg_price = past_period_df['거래금액(만원)'].mean()
            
            # 현재 기간별 상승률 계산
            period_data['과거대비상승률(%)'] = ((period_data['평균가'] - past_avg_price) / past_avg_price) * 100
            
            # 누적 상승률 계산 (첫 번째 기간을 기준으로)
            if len(period_data) > 0:
                first_price = period_data['평균가'].iloc[0]
                period_data['누적상승률(%)'] = ((period_data['평균가'] - first_price) / first_price) * 100
            
            # 상승률 추이 차트
            fig_trend_rising = go.Figure()
            
            fig_trend_rising.add_trace(go.Scatter(
                x=period_data['기간_한글'],
                y=period_data['과거대비상승률(%)'],
                name='과거 대비 상승률(%)',
                mode='lines+markers',
                line=dict(color='green', width=3),
                marker=dict(size=8),
                fill='tozeroy',
                fillcolor='rgba(0, 255, 0, 0.1)'
            ))
            
            # 누적 상승률 추가
            if len(period_data) > 0:
                fig_trend_rising.add_trace(go.Scatter(
                    x=period_data['기간_한글'],
                    y=period_data['누적상승률(%)'],
                    name='누적 상승률(%)',
                    mode='lines+markers',
                    line=dict(color='blue', width=2, dash='dash'),
                    marker=dict(size=6),
                    yaxis='y2'
                ))
            
            fig_trend_rising.add_hline(y=0, line_dash="dash", line_color="gray", opacity=0.5, annotation_text="기준선")
            
            fig_trend_rising.update_layout(
                title=f'{comparison_period} 대비 {analysis_unit} 가격 상승률 추이',
                xaxis_title=analysis_unit,
                yaxis=dict(title='과거 대비 상승률 (%)'),
                yaxis2=dict(title='누적 상승률 (%)', overlaying='y', side='right'),
                legend=dict(x=0, y=1.1, orientation='h'),
                hovermode="x unified"
            )
            st.plotly_chart(fig_trend_rising, use_container_width=True)
            
            # 3. 신고가 프리미엄 분석
            st.markdown("---")
            st.subheader("신고가 프리미엄 분석")
            st.markdown(f"과거 평균가 대비 현재 거래가의 프리미엄을 분석합니다. (비교 조건: {comparison_criteria})")
            
            # 각 거래의 프리미엄 계산 (비교 조건에 따라)
            premium_data = []
            for idx, row in current_period_df.iterrows():
                group_key = row['그룹키']
                current_price = row['거래금액(만원)']
                
                # 같은 그룹의 과거 평균가
                past_group_avg = past_period_df[past_period_df['그룹키'] == group_key]['거래금액(만원)'].mean()
                
                if pd.notna(past_group_avg) and past_group_avg > 0:
                    premium = current_price - past_group_avg
                    premium_rate = (premium / past_group_avg) * 100
                    premium_data.append({
                        '단지명': row['단지명'],
                        '거래금액': current_price,
                        '과거평균가': past_group_avg,
                        '프리미엄': premium,
                        '프리미엄률(%)': premium_rate,
                        '거래일자': row['거래일자']
                    })
            
            if premium_data:
                premium_df = pd.DataFrame(premium_data)
                
                col_premium1, col_premium2 = st.columns(2)
                
                with col_premium1:
                    # 프리미엄 분포 히스토그램
                    fig_premium_hist = px.histogram(
                        premium_df,
                        x='프리미엄',
                        nbins=30,
                        title='신고가 프리미엄 분포',
                        labels={'프리미엄': '프리미엄(만원)'},
                        color_discrete_sequence=['#FF6B6B']
                    )
                    fig_premium_hist.add_vline(x=0, line_dash="dash", line_color="gray", opacity=0.5)
                    st.plotly_chart(fig_premium_hist, use_container_width=True)
                
                with col_premium2:
                    # 프리미엄률 분포 히스토그램
                    fig_premium_rate_hist = px.histogram(
                        premium_df,
                        x='프리미엄률(%)',
                        nbins=30,
                        title='신고가 프리미엄률 분포',
                        labels={'프리미엄률(%)': '프리미엄률(%)'},
                        color_discrete_sequence=['#4ECDC4']
                    )
                    fig_premium_rate_hist.add_vline(x=0, line_dash="dash", line_color="gray", opacity=0.5)
                    st.plotly_chart(fig_premium_rate_hist, use_container_width=True)
                
                # 프리미엄이 높은 거래 TOP 10
                st.markdown("---")
                st.subheader("프리미엄이 높은 거래 TOP 10")
                top_premium = premium_df.nlargest(10, '프리미엄')[['단지명', '거래일자', '거래금액', '과거평균가', '프리미엄', '프리미엄률(%)']].copy()
                top_premium['거래일자'] = top_premium['거래일자'].dt.strftime('%Y-%m-%d')
                top_premium['거래금액'] = top_premium['거래금액'].round(0).astype(int)
                top_premium['과거평균가'] = top_premium['과거평균가'].round(0).astype(int)
                top_premium['프리미엄'] = top_premium['프리미엄'].round(0).astype(int)
                top_premium['프리미엄률(%)'] = top_premium['프리미엄률(%)'].round(2)
                top_premium.columns = ['단지명', '거래일자', '거래금액(만원)', '과거평균가(만원)', '프리미엄(만원)', '프리미엄률(%)']
                st.dataframe(top_premium, use_container_width=True, hide_index=True)
                
                # 시간별 프리미엄 추이
                st.markdown("---")
                st.subheader("시간별 프리미엄 추이")
                premium_df['년월'] = premium_df['거래일자'].dt.to_period('M').astype(str)
                premium_df['년월_한글'] = premium_df['년월'].apply(format_yearmonth_korean)
                
                monthly_premium = premium_df.groupby('년월_한글').agg({
                    '프리미엄': 'mean',
                    '프리미엄률(%)': 'mean'
                }).reset_index()
                
                fig_premium_trend = go.Figure()
                
                fig_premium_trend.add_trace(go.Scatter(
                    x=monthly_premium['년월_한글'],
                    y=monthly_premium['프리미엄'],
                    name='평균 프리미엄(만원)',
                    mode='lines+markers',
                    line=dict(color='blue', width=3),
                    marker=dict(size=8),
                    yaxis='y'
                ))
                
                fig_premium_trend.add_trace(go.Scatter(
                    x=monthly_premium['년월_한글'],
                    y=monthly_premium['프리미엄률(%)'],
                    name='평균 프리미엄률(%)',
                    mode='lines+markers',
                    line=dict(color='red', width=3, dash='dash'),
                    marker=dict(size=8),
                    yaxis='y2'
                ))
                
                fig_premium_trend.update_layout(
                    title='월별 평균 프리미엄 및 프리미엄률 추이',
                    xaxis_title='년월',
                    yaxis=dict(title='평균 프리미엄(만원)'),
                    yaxis2=dict(title='평균 프리미엄률(%)', overlaying='y', side='right'),
                    legend=dict(x=0, y=1.1, orientation='h'),
                    hovermode="x unified"
                )
                # y축 금액 레이블을 한글로 변환
                max_premium = monthly_premium['프리미엄'].max()
                fig_premium_trend = format_price_axis(fig_premium_trend, axis='y', max_value=max_premium)
                st.plotly_chart(fig_premium_trend, use_container_width=True)
            else:
                st.info("프리미엄 분석을 위한 데이터가 충분하지 않습니다.")

if __name__ == "__main__":
    main()

