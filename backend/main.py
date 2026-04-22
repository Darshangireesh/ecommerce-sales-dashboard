import os
import pandas as pd
from fastapi import FastAPI, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, Response
from fastapi.middleware.cors import CORSMiddleware
import io

app = FastAPI(title="E-Commerce Sales Insights API")

# Setup CORS just in case frontend isn't served statically later
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global store for the processed dataframe
df = pd.DataFrame()

@app.on_event("startup")
def load_and_process_data():
    global df
    # Build path relative to the root directory just in case it means /data in workspace
    workspace_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    file_path = os.path.join(workspace_dir, "data", "sales_data.csv")
    
    # If the user literally meant the absolute system path /data/sales_data.csv on unix/windows
    if not os.path.exists(file_path):
        file_path = "/data/sales_data.csv"
    
    if not os.path.exists(file_path):
        print(f"Warning: Dataset not found at {file_path}")
        return

    print("Loading data...")
    # Load dataset
    raw_df = pd.read_csv(file_path)
    
    # 1. Convert Order Date to datetime format
    raw_df['Order Date'] = pd.to_datetime(raw_df['Order Date'], errors='coerce')
    
    # 2. Add unit_price column
    if 'Sales' in raw_df.columns and 'Quantity' in raw_df.columns:
        raw_df['unit_price'] = raw_df['Sales'] / raw_df['Quantity']
        
    # 3. Handle missing values
    num_cols = raw_df.select_dtypes(include=['number']).columns
    cat_cols = raw_df.select_dtypes(include=['object', 'category']).columns
    
    raw_df[num_cols] = raw_df[num_cols].fillna(0)
    raw_df[cat_cols] = raw_df[cat_cols].fillna('Unknown')
    
    # Remove rows where Order Date is missing just to be safe
    raw_df = raw_df.dropna(subset=['Order Date'])
    
    # Pre-calculate year-month
    raw_df['YearMonth'] = raw_df['Order Date'].dt.strftime('%Y-%m')
    
    df = raw_df
    print(f"Data loaded successfully. Rows: {len(df)}")

def filter_data(start_date: str = None, end_date: str = None, region: str = None, category: str = None):
    filtered = df.copy()
    if start_date:
        filtered = filtered[filtered['Order Date'] >= pd.to_datetime(start_date)]
    if end_date:
        filtered = filtered[filtered['Order Date'] <= pd.to_datetime(end_date)]
    if region and region != 'All':
        filtered = filtered[filtered['Region'] == region]
    if category and category != 'All':
        filtered = filtered[filtered['Category'] == category]
    return filtered

@app.get("/api/kpis")
def get_kpis(start: str = Query(None), end: str = Query(None), region: str = Query(None), category: str = Query(None)):
    if df.empty: return {}
    fd = filter_data(start, end, region, category)
    total_sales = float(fd['Sales'].sum()) if 'Sales' in fd else 0
    total_orders = int(fd['Order ID'].nunique()) if 'Order ID' in fd else 0
    aov = float(total_sales / total_orders) if total_orders > 0 else 0
    total_profit = float(fd['Profit'].sum()) if 'Profit' in fd else 0

    return {
        "total_sales": total_sales,
        "total_orders": total_orders,
        "average_order_value": aov,
        "total_profit": total_profit
    }

@app.get("/api/sales_by_month")
def sales_by_month(start: str = Query(None), end: str = Query(None), region: str = Query(None), category: str = Query(None)):
    if df.empty: return []
    fd = filter_data(start, end, region, category)
    grouped = fd.groupby('YearMonth')['Sales'].sum().reset_index()
    grouped.sort_values('YearMonth', inplace=True)
    return {
        "labels": grouped['YearMonth'].tolist(),
        "values": grouped['Sales'].tolist()
    }

@app.get("/api/top_products")
def top_products(start: str = Query(None), end: str = Query(None), region: str = Query(None), category: str = Query(None)):
    if df.empty: return []
    fd = filter_data(start, end, region, category)
    if 'Product Name' not in fd: return []
    grouped = fd.groupby('Product Name')['Sales'].sum().reset_index()
    top10 = grouped.sort_values('Sales', ascending=False).head(10)
    return {
        "labels": top10['Product Name'].tolist(),
        "values": top10['Sales'].tolist()
    }

@app.get("/api/region_sales")
def region_sales(start: str = Query(None), end: str = Query(None), region: str = Query(None), category: str = Query(None)):
    if df.empty: return []
    fd = filter_data(start, end, region, category)
    grouped = fd.groupby('Region')['Sales'].sum().reset_index()
    return {
        "labels": grouped['Region'].tolist(),
        "values": grouped['Sales'].tolist()
    }

@app.get("/api/category_sales")
def category_sales(start: str = Query(None), end: str = Query(None), region: str = Query(None), category: str = Query(None)):
    if df.empty: return []
    fd = filter_data(start, end, region, category)
    grouped = fd.groupby('Category')['Sales'].sum().reset_index()
    return {
        "labels": grouped['Category'].tolist(),
        "values": grouped['Sales'].tolist()
    }

@app.get("/api/profit_vs_discount")
def profit_vs_discount(start: str = Query(None), end: str = Query(None), region: str = Query(None), category: str = Query(None)):
    if df.empty: return []
    fd = filter_data(start, end, region, category)
    # Downsample slightly if it's too large so the chart doesn't freeze
    if len(fd) > 1000:
        fd = fd.sample(1000, random_state=42)
        
    return {
        "data": fd[['Discount', 'Profit']].rename(columns={"Discount": "x", "Profit": "y"}).to_dict(orient="records")
    }

@app.get("/api/filters")
def get_filters():
    if df.empty: return {}
    # Use standard Python types for JSON serialization
    regions = ['All'] + df['Region'].dropna().unique().tolist()
    categories = ['All'] + df['Category'].dropna().unique().tolist()
    min_date = df['Order Date'].min().strftime('%Y-%m-%d')
    max_date = df['Order Date'].max().strftime('%Y-%m-%d')
    return {
        "regions": regions,
        "categories": categories,
        "date_bounds": {
            "min": min_date,
            "max": max_date
        }
    }

@app.get("/api/report")
def export_report(start: str = Query(None), end: str = Query(None), region: str = Query(None), category: str = Query(None)):
    if df.empty: return Response(content="No data", media_type="text/plain")
    fd = filter_data(start, end, region, category)
    
    stream = io.StringIO()
    fd.to_csv(stream, index=False)
    
    response = Response(content=stream.getvalue(), media_type="text/csv")
    response.headers["Content-Disposition"] = "attachment; filename=sales_report.csv"
    return response

@app.get("/api/smart_insights")
def smart_insights(start: str = Query(None), end: str = Query(None), region: str = Query(None), category: str = Query(None)):
    if df.empty: return {}
    fd = filter_data(start, end, region, category)
    if fd.empty: return {"insights": [], "summary": "No data available for the current filters.", "trend_color": "red"}

    total_sales = float(fd['Sales'].sum())
    
    # 1. Top region
    if 'Region' in fd.columns and not fd['Region'].empty:
        reg_sales = fd.groupby('Region')['Sales'].sum()
        top_region = reg_sales.idxmax()
        top_reg_val = reg_sales.max()
        reg_str = f"The highest sales are generated from {top_region} with total revenue of ₹{top_reg_val:,.2f}."
    else: reg_str = "Region insights unavailable."

    # 2. Best selling category
    if 'Category' in fd.columns and total_sales > 0:
        cat_sales = fd.groupby('Category')['Sales'].sum()
        top_cat = cat_sales.idxmax()
        top_cat_pct = (cat_sales.max() / total_sales) * 100
        cat_str = f"The most popular product category is {top_cat}, contributing {top_cat_pct:.1f}% of total sales."
    else: cat_str = "Category insights unavailable."

    # 3. Most profitable segment
    if 'Segment' in fd.columns and 'Profit' in fd.columns:
        seg_profit = fd.groupby('Segment')['Profit'].sum()
        top_seg = seg_profit.idxmax()
        top_seg_val = seg_profit.max()
        seg_str = f"The {top_seg} segment yields the highest profit of ₹{top_seg_val:,.2f}."
    else: seg_str = "Segment insights unavailable."

    # 4. Monthly trend
    trend_color = "green"
    trend_str = "Sales show a stable trend."
    if 'YearMonth' in fd.columns:
        monthly_sales = fd.groupby('YearMonth')['Sales'].sum().sort_index()
        if len(monthly_sales) >= 2:
            first_half = monthly_sales.iloc[:len(monthly_sales)//2].mean()
            second_half = monthly_sales.iloc[len(monthly_sales)//2:].mean()
            if second_half > first_half:
                trend_str = "Sales show an increasing trend over the selected period."
            elif second_half < first_half:
                trend_str = "Sales show a decreasing trend over the selected period."
                trend_color = "red"

    # 5. Discount impact
    if 'Discount' in fd.columns and 'Profit' in fd.columns:
        high_discount = fd[fd['Discount'] >= 0.2]
        low_discount = fd[fd['Discount'] < 0.2]
        high_margin = (high_discount['Profit'].sum() / high_discount['Sales'].sum()) if high_discount['Sales'].sum() > 0 else 0
        low_margin = (low_discount['Profit'].sum() / low_discount['Sales'].sum()) if low_discount['Sales'].sum() > 0 else 0
        
        if high_margin < low_margin:
            disc_str = f"Higher discounts (above 20%) are reducing profit margins significantly compared to lower discounts."
        else:
            disc_str = f"Discounts are currently maintaining steady profit margins."
    else: disc_str = "Discount insights unavailable."

    # 6. Top product
    if 'Product Name' in fd.columns:
        prod_sales = fd.groupby('Product Name')['Sales'].sum()
        top_prod = prod_sales.idxmax()
        top_prod_val = prod_sales.max()
        prod_str = f"The top-selling product is {top_prod} with revenue ₹{top_prod_val:,.2f}."
    else: prod_str = "Product insights unavailable."

    # Extract dynamic parts for summary safely
    s_seg = top_seg if 'Segment' in fd.columns else "N/A"
    s_cat = top_cat if 'Category' in fd.columns else "N/A"

    summary = f"Overall Business Performance: The business has generated ₹{total_sales:,.2f} in this period. The {s_seg} segment and {s_cat} category are clearly driving profitability. Attention is recommended towards discount optimization to ensure maximum margins."

    return {
        "insights": [
            {"text": reg_str, "icon": "🌍"},
            {"text": cat_str, "icon": "📦"},
            {"text": seg_str, "icon": "💎"},
            {"text": trend_str, "icon": "📈" if trend_color == "green" else "📉"},
            {"text": disc_str, "icon": "🏷️"},
            {"text": prod_str, "icon": "🏆"}
        ],
        "summary": summary,
        "trend_color": trend_color
    }

# Static files should be mounted LAST so it doesn't mask /api routes
frontend_path = os.path.join(os.path.dirname(__file__), "..", "frontend")
if os.path.exists(frontend_path):
    app.mount("/", StaticFiles(directory=frontend_path, html=True), name="frontend")
else:
    @app.get("/")
    def no_frontend():
        return {"message": "Frontend not found"}
