"""
Crypto Market Cap Dashboard.

Local run:
    python dashboard/app.py
    -> http://127.0.0.1:8050

Production (Render): gunicorn runs this via the `server` object below,
using the command in the Procfile. Render assigns the port dynamically
via the PORT environment variable, so we never hardcode 8050 for prod.
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import dash
from dash import dcc, html, Input, Output
import plotly.express as px
import plotly.graph_objects as go

from dashboard.data import (
    get_latest_date,
    get_top_movers,
    get_volatility_leaderboard,
    get_consistent_movers,
    get_market_cap_trend,
    get_pipeline_health,
    get_data_completeness,
)
from dashboard.news import get_news_with_sentiment_for_coin

app = dash.Dash(__name__, title="Crypto Market Dashboard")
server = app.server  # gunicorn (Render) imports this - Dash's Flask instance underneath

CARD_STYLE = {
    "backgroundColor": "#ffffff",
    "borderRadius": "8px",
    "padding": "20px",
    "boxShadow": "0 1px 3px rgba(0,0,0,0.1)",
    "marginBottom": "20px",
}

app.layout = html.Div(
    style={"backgroundColor": "#f5f6fa", "fontFamily": "Arial, sans-serif", "padding": "30px"},
    children=[
        html.H1("Crypto Market Cap Analytics", style={"marginBottom": "4px"}),
        html.P(
            "Data collected via CoinMarketCap API, top 50 coins by market cap, "
            "refreshed automatically via a scheduled cloud pipeline.",
            style={"color": "#666", "marginBottom": "24px"},
        ),
        dcc.Tabs(
            id="tabs",
            value="movers",
            children=[
                dcc.Tab(label="Top Movers", value="movers"),
                dcc.Tab(label="Why It Moved (News)", value="news"),
                dcc.Tab(label="Volatility Leaderboard", value="volatility"),
                dcc.Tab(label="Consistent Movers", value="consistent"),
                dcc.Tab(label="Market Cap Trends", value="trends"),
                dcc.Tab(label="Pipeline Health", value="health"),
            ],
        ),
        html.Div(id="tab-content", style={"marginTop": "20px"}),
    ],
)


@app.callback(Output("tab-content", "children"), Input("tabs", "value"))
def render_tab(tab):
    if tab == "movers":
        return render_movers_tab()
    elif tab == "news":
        return render_news_tab()
    elif tab == "volatility":
        return render_volatility_tab()
    elif tab == "consistent":
        return render_consistent_tab()
    elif tab == "trends":
        return render_trends_tab()
    elif tab == "health":
        return render_health_tab()


def render_movers_tab():
    latest_date = get_latest_date()
    gainers = get_top_movers(latest_date, direction="gainers", limit=10)
    losers = get_top_movers(latest_date, direction="losers", limit=10)

    gainers_fig = px.bar(
        gainers, x="pct_change_intraday", y="name", orientation="h",
        title=f"Top Gainers - {latest_date}", color_discrete_sequence=["#2ecc71"],
        labels={"pct_change_intraday": "% Change", "name": ""},
    )
    gainers_fig.update_layout(yaxis={"categoryorder": "total ascending"})

    losers_fig = px.bar(
        losers, x="pct_change_intraday", y="name", orientation="h",
        title=f"Top Losers - {latest_date}", color_discrete_sequence=["#e74c3c"],
        labels={"pct_change_intraday": "% Change", "name": ""},
    )
    losers_fig.update_layout(yaxis={"categoryorder": "total descending"})

    return html.Div([
        html.Div(dcc.Graph(figure=gainers_fig), style=CARD_STYLE),
        html.Div(dcc.Graph(figure=losers_fig), style=CARD_STYLE),
    ])


def render_news_tab():
    latest_date = get_latest_date()
    top_gainers = get_top_movers(latest_date, direction="gainers", limit=3)
    top_losers = get_top_movers(latest_date, direction="losers", limit=3)

    coins_to_check = list(top_gainers.itertuples()) + list(top_losers.itertuples())
    sentiment_color = {"Positive": "#2ecc71", "Negative": "#e74c3c", "Neutral": "#95a5a6", "No coverage found": "#bdc3c7"}

    cards = []
    for coin in coins_to_check:
        # one Currents API search call per coin (keyword-driven endpoint,
        # not a bulk feed we filter client-side) - stays within the 250/day
        # free quota easily at 6 coins x however often the page is loaded
        result = get_news_with_sentiment_for_coin(coin.name, coin.symbol)
        headline_items = [
            html.Li([
                html.A(a["title"], href=a["link"], target="_blank", style={"color": "#2c3e50"}),
                html.Span(f"  ({a['source']}, {a['sentiment_label']})", style={"color": "#888", "fontSize": "12px"}),
            ])
            for a in result["articles"]
        ] or [html.Li("No recent headlines matched this coin.", style={"color": "#999"})]

        cards.append(html.Div([
            html.Div([
                html.Span(f"{coin.name} ({coin.symbol})", style={"fontWeight": "bold", "fontSize": "16px"}),
                html.Span(f"  {coin.pct_change_intraday:+.2f}%", style={"color": "#2ecc71" if coin.pct_change_intraday >= 0 else "#e74c3c", "marginLeft": "10px"}),
                html.Span(
                    result["overall_sentiment"],
                    style={
                        "backgroundColor": sentiment_color.get(result["overall_sentiment"], "#ccc"),
                        "color": "white", "borderRadius": "4px", "padding": "2px 8px",
                        "marginLeft": "10px", "fontSize": "12px",
                    },
                ),
            ]),
            html.Ul(headline_items, style={"marginTop": "8px"}),
        ], style=CARD_STYLE))

    note = html.P(
        "Matches today's biggest gainers/losers against live news search (Currents API), "
        "with sentiment scored via offline NLP (VADER). Live/current-day only.",
        style={"color": "#666", "fontSize": "13px"},
    )
    return html.Div([note] + cards)


def render_volatility_tab():
    df = get_volatility_leaderboard(limit=15)
    fig = px.bar(
        df, x="volatility_pct_of_price", y="name", orientation="h",
        title="Volatility Leaderboard (volatility as % of avg price)",
        color_discrete_sequence=["#9b59b6"],
        labels={"volatility_pct_of_price": "Volatility (% of price)", "name": ""},
        hover_data=["symbol", "avg_price", "days_tracked"],
    )
    fig.update_layout(yaxis={"categoryorder": "total ascending"})
    note = html.P(
        "Volatility shown relative to price, so a $60,000 coin and a $0.05 coin can be "
        "compared fairly. Coins need at least 3 tracked days to appear here.",
        style={"color": "#666", "fontSize": "13px"},
    )
    return html.Div([note, html.Div(dcc.Graph(figure=fig), style=CARD_STYLE)])


def render_consistent_tab():
    df = get_consistent_movers(limit=15)
    fig = px.bar(
        df, x="days_in_top10", y="name", orientation="h",
        title="Coins Most Frequently in the Daily Top-10 Movers",
        color="avg_pct_change", color_continuous_scale="RdYlGn",
        labels={"days_in_top10": "Days as a Top-10 Mover", "name": "", "avg_pct_change": "Avg % Change"},
        hover_data=["symbol"],
    )
    fig.update_layout(yaxis={"categoryorder": "total ascending"})
    note = html.P(
        "Coins that repeatedly show up as a top-10 mover across multiple different days - "
        "a sign of a genuine trend rather than a one-off spike.",
        style={"color": "#666", "fontSize": "13px"},
    )
    return html.Div([note, html.Div(dcc.Graph(figure=fig), style=CARD_STYLE)])


def render_trends_tab():
    df = get_market_cap_trend(top_n=10)
    fig = px.line(
        df, x="summary_date", y="avg_market_cap", color="name",
        title="Market Cap Trend - Top 10 Coins",
        labels={"summary_date": "Date", "avg_market_cap": "Market Cap (USD)", "name": "Coin"},
    )
    fig.update_layout(legend=dict(orientation="v"))
    return html.Div([html.Div(dcc.Graph(figure=fig), style=CARD_STYLE)])


def render_health_tab():
    health_df = get_pipeline_health()
    completeness_df = get_data_completeness()

    health_fig = px.bar(
        health_df, x="run_type", y="run_count", color="status",
        title="Pipeline Run Outcomes",
        color_discrete_map={"success": "#2ecc71", "failure": "#e74c3c"},
        labels={"run_type": "Step", "run_count": "Number of Runs"},
    )

    completeness_fig = go.Figure()
    completeness_fig.add_trace(go.Bar(
        x=completeness_df["summary_date"].astype(str),
        y=completeness_df["coins_tracked"],
        name="Coins Tracked", marker_color="#3498db",
    ))
    completeness_fig.add_trace(go.Scatter(
        x=completeness_df["summary_date"].astype(str),
        y=completeness_df["avg_snapshots"],
        name="Avg Snapshots/Coin", yaxis="y2", marker_color="#e67e22",
    ))
    completeness_fig.update_layout(
        title="Data Completeness by Day",
        yaxis=dict(title="Coins Tracked"),
        yaxis2=dict(title="Avg Snapshots/Coin", overlaying="y", side="right"),
    )

    return html.Div([
        html.Div(dcc.Graph(figure=health_fig), style=CARD_STYLE),
        html.Div(dcc.Graph(figure=completeness_fig), style=CARD_STYLE),
    ])


if __name__ == "__main__":
    # local dev only - Render uses gunicorn + the `server` object instead of this
    port = int(os.getenv("PORT", 8050))
    app.run(debug=True, host="0.0.0.0", port=port)
