import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import time
from datetime import datetime
from scipy.stats import norm

# Page configuration
st.set_page_config(page_title="Stock Tracker PRO", layout="wide")
st.title("📈 Stock Tracker, Options & Equity Entry Engine")

if "tickers" not in st.session_state:
    st.session_state.tickers = ["RKLB", "PLTR", "CRCL", "CRWV", "OKLO", "SMCI"]

# --- CACHING ENGINE: PROTECTS AGAINST RATE LIMITS ---
@st.cache_data(ttl=300, show_spinner=False)
def get_macro_data():
    try:
        nq = yf.download("NQ=F", period="5d", progress=False)
        if isinstance(nq.columns, pd.MultiIndex):
            nq.columns = nq.columns.droplevel(1)
        return nq
    except Exception:
        return pd.DataFrame()

@st.cache_data(ttl=300, show_spinner=False)
def get_stock_data(ticker):
    time.sleep(0.5)
    try:
        df = yf.download(ticker, period="1y", progress=False)
        live_df = yf.download(ticker, period="1d", interval="1m", prepost=True, progress=False)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.droplevel(1)
        if isinstance(live_df.columns, pd.MultiIndex):
            live_df.columns = live_df.columns.droplevel(1)
            
        tk = yf.Ticker(ticker)
        
        tk_info = tk.info if hasattr(tk, 'info') else {}
        tk_news = tk.news if hasattr(tk, 'news') else []
        tk_options = tk.options if hasattr(tk, 'options') else []
        
        try:
            tk_insider = tk.insider_transactions
        except Exception:
            tk_insider = None
            
        return df, live_df, tk_info, tk_news, tk_options, tk_insider
    except Exception:
        return pd.DataFrame(), pd.DataFrame(), {}, [], [], None

@st.cache_data(ttl=300, show_spinner=False)
def get_option_chains(ticker, valid_exps_list):
    all_opts = pd.DataFrame()
    tk = yf.Ticker(ticker)
    for exp, dte in valid_exps_list:
        try:
            chain = tk.option_chain(exp)
            calls = chain.calls
            calls['opt_type'] = 'Call'
            calls['expiration'] = exp
            calls['dte'] = max(dte, 1)
            
            puts = chain.puts
            puts['opt_type'] = 'Put'
            puts['expiration'] = exp
            puts['dte'] = max(dte, 1)
            
            all_opts = pd.concat([all_opts, calls, puts], ignore_index=True)
        except Exception:
            pass
    return all_opts

# --- Sidebar: Ticker Management ---
st.sidebar.header("Manage Tickers")

with st.sidebar.form("add_ticker_form", clear_on_submit=True):
    new_ticker = st.text_input("Add a Ticker")
    submitted = st.form_submit_button("Add")
    if submitted and new_ticker:
        ticker_upper = new_ticker.strip().upper()
        if ticker_upper not in st.session_state.tickers:
            st.session_state.tickers.append(ticker_upper)
            st.rerun()

st.sidebar.divider()
st.sidebar.subheader("Currently Tracking:")

for ticker in st.session_state.tickers:
    col1, col2 = st.sidebar.columns([3, 1])
    col1.write(f"**{ticker}**")
    if col2.button("❌", key=f"del_{ticker}"):
        st.session_state.tickers.remove(ticker)
        st.rerun()

# --- Global Market Sentiment (Futures) ---
st.sidebar.divider()
st.sidebar.subheader("Macro Sentiment")
nq_change_pct = 0.0
futures_modifier = 0.0
futures_status = "Neutral"

with st.sidebar:
    nq_data = get_macro_data()
    if not nq_data.empty:
        nq_last = float(nq_data['Close'].dropna().iloc[-1])
        nq_prev = float(nq_data['Close'].dropna().iloc[-2])
        nq_change_pct = ((nq_last - nq_prev) / nq_prev) * 100
        
        if nq_change_pct >= 0.5:
            st.success(f"**Nasdaq Futures:**  \n🚀 +{nq_change_pct:.2f}%  \n*(Bullish)*")
            futures_modifier = 1.0
            futures_status = "Tailwind"
        elif nq_change_pct <= -0.5:
            st.error(f"**Nasdaq Futures:**  \n🩸 {nq_change_pct:.2f}%  \n*(Bearish)*")
            futures_modifier = -1.0
            futures_status = "Headwind"
        else:
            st.info(f"**Nasdaq Futures:**  \n⚖️ {nq_change_pct:.2f}%  \n*(Neutral)*")
            futures_modifier = 0.0
    else:
        st.warning("Could not load Futures data.")

# --- Main Page: Data & Charts ---
if not st.session_state.tickers:
    st.info("No tickers to display. Add some from the sidebar!")
else:
    tabs = st.tabs(st.session_state.tickers)
    
    for idx, ticker in enumerate(st.session_state.tickers):
        with tabs[idx]:
            st.subheader(f"{ticker} Analysis & Strategy")
            
            with st.spinner(f"Loading cached data for {ticker}..."):
                df, live_df, tk_info, news, exps, insider_df = get_stock_data(ticker)
            
            if df.empty:
                st.warning(f"Could not load data for {ticker}. Yahoo API may be temporarily blocking requests.")
            else:
                if not live_df.empty and not live_df['Close'].dropna().empty:
                    curr_price = float(live_df['Close'].dropna().iloc[-1])
                    df.at[df.index[-1], 'Close'] = curr_price
                else:
                    curr_price = float(df['Close'].dropna().iloc[-1])
                
                vol = int(df['Volume'].dropna().iloc[-1])
                vol_str = f"{vol / 1_000_000_000:.2f}B" if vol >= 1_000_000_000 else (f"{vol / 1_000_000:.2f}M" if vol >= 1_000_000 else f"{vol:,}")
                    
                shares = tk_info.get('sharesOutstanding')
                shares_str = "N/A"
                if shares:
                    shares_str = f"{shares / 1_000_000_000:.2f}B" if shares >= 1_000_000_000 else (f"{shares / 1_000_000:.2f}M" if shares >= 1_000_000 else f"{shares:,}")
                    
                mkt_cap = tk_info.get('marketCap')
                cap_str = "N/A"
                if mkt_cap:
                     cap_str = f"${mkt_cap / 1_000_000_000_000:.2f}T" if mkt_cap >= 1_000_000_000_000 else (f"${mkt_cap / 1_000_000_000:.2f}B" if mkt_cap >= 1_000_000_000 else f"${mkt_cap / 1_000_000:.2f}M")
                     
                df['Daily_Return'] = df['Close'].pct_change()
                hist_vol = df['Daily_Return'].tail(30).std() * np.sqrt(252)
                hist_vol = max(hist_vol, 0.25)
                
                delta = df['Close'].diff()
                gain = delta.where(delta > 0, 0.0).ewm(alpha=1/14, adjust=False).mean()
                loss = (-delta.where(delta < 0, 0.0)).ewm(alpha=1/14, adjust=False).mean()
                rs = gain / loss
                df['RSI'] = 100 - (100 / (1 + rs))
                
                df['Overbought (70)'] = 70
                df['Oversold (30)'] = 30
                
                df['EMA_12'] = df['Close'].ewm(span=12, adjust=False).mean()
                df['EMA_26'] = df['Close'].ewm(span=26, adjust=False).mean()
                df['MACD'] = df['EMA_12'] - df['EMA_26']
                df['Signal_Line'] = df['MACD'].ewm(span=9, adjust=False).mean()

                df['EMA_20'] = df['Close'].ewm(span=20, adjust=False).mean()
                df['Support_20'] = df['Close'].rolling(window=20).min()
                
                ema_20_val = float(df.iloc[-1]['EMA_20'])
                support_20_val = float(df.iloc[-1]['Support_20'])

                expected_1w_move = df['Close'].diff(5).abs().tail(21).mean()
                if pd.isna(expected_1w_move) or expected_1w_move < (curr_price * 0.02):
                    expected_1w_move = curr_price * 0.025

                latest = df.iloc[-1]
                prev = df.iloc[-2] if len(df) > 1 else latest
                
                rsi_val = float(latest['RSI'])
                macd_val = float(latest['MACD'])
                sig_val = float(latest['Signal_Line'])
                prev_macd = float(prev['MACD'])
                prev_sig = float(prev['Signal_Line'])
                
                score = 0
                rsi_reason = "Neutral"
                macd_reason = "Neutral"
                
                if rsi_val >= 70: score -= 2; rsi_reason = "Overbought"
                elif rsi_val >= 55: score -= 1; rsi_reason = "Trending Hot"
                elif rsi_val <= 30: score += 2; rsi_reason = "Oversold"
                elif rsi_val <= 45: score += 1; rsi_reason = "Trending Cool"
                    
                if prev_macd <= prev_sig and macd_val > sig_val: score += 2; macd_reason = "Bullish Crossover"
                elif prev_macd >= prev_sig and macd_val < sig_val: score -= 2; macd_reason = "Bearish Crossover"
                elif macd_val > sig_val: score += 0.5; macd_reason = "Bullish Momentum"
                else: score -= 0.5; macd_reason = "Bearish Momentum"
                    
                # 1. News Sentiment
                news_score = 0.0
                news_sentiment_reason = "Neutral"
                if news:
                    pos_words = ['buyback', 'upgrade', 'beat', 'surge', 'raised', 'bull']
                    neg_words = ['downgrade', 'miss', 'sell', 'cut', 'lawsuit', 'bear', 'drop']
                    pos_count = sum(1 for a in news if any(w in a.get('title', '').lower() for w in pos_words))
                    neg_count = sum(1 for a in news if any(w in a.get('title', '').lower() for w in neg_words))
                    if pos_count > neg_count:
                        news_score = 1.0; news_sentiment_reason = "Bullish Catalysts"
                    elif neg_count > pos_count:
                        news_score = -1.0; news_sentiment_reason = "Bearish Headwinds"
                
                # 2. Insider Sentiment (BULLETPROOF FIX)
                insider_score = 0.0
                insider_sentiment_reason = "No Recent Action"
                if insider_df is not None and not insider_df.empty:
                    try:
                        # Explicitly cast every single value to string before joining
                        insider_text = insider_df.apply(lambda row: ' '.join([str(val) for val in row]), axis=1).str.lower()
                        recent_buys = insider_text.str.contains('buy|purchase').sum()
                        recent_sells = insider_text.str.contains('sale|sell').sum()
                        if recent_buys > recent_sells:
                            insider_score = 1.0; insider_sentiment_reason = "Bullish (Accumulation)"
                        elif recent_sells > recent_buys:
                            insider_score = -1.0; insider_sentiment_reason = "Bearish (Distribution)"
                        else:
                            insider_sentiment_reason = "Mixed Action"
                    except Exception:
                        pass
                    
                score += futures_modifier + news_score + insider_score
                    
                if score >= 2.5: signal = "🟢 STRONG BUY"
                elif score >= 0.5: signal = "🟢 BUY"
                elif score <= -2.5: signal = "🔴 STRONG SELL"
                elif score <= -0.5: signal = "🔴 SELL"
                else: signal = "🟡 HOLD / NEUTRAL"

                st.markdown(f"### Current Trend: {signal}")
                
                col_strat1, col_strat2 = st.columns(2)
                
                with col_strat1:
                    st.subheader("📦 Equity Target")
                    if score > 0:
                        if rsi_val > 55: st.info(f"**Pullback Target:** ${ema_20_val:.2f} (20-Day EMA).")
                        else: st.info(f"**Accumulation Target:** ${max(support_20_val, curr_price * 0.98):.2f}.")
                    elif score < 0: st.info(f"**Short Target:** ${ema_20_val:.2f} (20-Day EMA).")
                    else: st.info("**No Clear Edge:** Consolidating sideways.")
                    
                with col_strat2:
                    st.subheader("🎯 Probabilistic Options Engine")
                    if score >= 0.5 or score <= -0.5:
                        if st.button(f"Generate 25% Min ROI & POP% for {ticker}", key=f"btn_{ticker}"):
                            with st.spinner("Calculating Probability of Profit (POP)..."):
                                if not exps:
                                    st.warning("⚠️ No options data available.")
                                else:
                                    today = datetime.today()
                                    valid_exps = []
                                    for exp in exps:
                                        days_out = (datetime.strptime(exp, '%Y-%m-%d') - today).days
                                        if 3 <= days_out <= 45:
                                            valid_exps.append((exp, days_out))
                                            
                                    if not valid_exps:
                                        st.warning("⚠️ No expirations found in the 3 to 45-day window.")
                                    else:
                                        all_opts = get_option_chains(ticker, valid_exps[:4])
                                        
                                        if all_opts.empty:
                                            st.warning("⚠️ Option chains are currently empty.")
                                        else:
                                            opt_type = "Call" if score > 0 else "Put"
                                            all_opts = all_opts[all_opts['opt_type'] == opt_type].copy()
                                            
                                            all_opts['ask'] = all_opts['ask'].fillna(0)
                                            all_opts['bid'] = all_opts['bid'].fillna(0)
                                            all_opts['lastPrice'] = all_opts['lastPrice'].fillna(0)
                                            all_opts['effective_price'] = np.where(all_opts['ask'] > 0, all_opts['ask'], all_opts['lastPrice'])
                                            
                                            safe_opts = all_opts[
                                                (all_opts['effective_price'] <= 8.0) & 
                                                (all_opts['effective_price'] >= 0.10)
                                            ].copy()
                                            
                                            if safe_opts.empty:
                                                st.warning("⚠️ No active options passed liquidity filters.")
                                            else:
                                                if score > 0: # Bullish
                                                    safe_opts['breakeven'] = safe_opts['strike'] + safe_opts['effective_price']
                                                    target_price = curr_price + expected_1w_move
                                                    safe_opts['est_intrinsic'] = np.maximum(0, target_price - safe_opts['strike'])
                                                else: # Bearish
                                                    safe_opts['breakeven'] = safe_opts['strike'] - safe_opts['effective_price']
                                                    target_price = curr_price - expected_1w_move
                                                    safe_opts['est_intrinsic'] = np.maximum(0, safe_opts['strike'] - target_price)
                                                
                                                safe_opts['est_roi'] = (safe_opts['est_intrinsic'] - safe_opts['effective_price']) / safe_opts['effective_price']
                                                safe_opts['time_to_exp_years'] = safe_opts['dte'] / 365.0
                                                
                                                if score > 0:
                                                    safe_opts['d2'] = (np.log(curr_price / safe_opts['breakeven']) + (0.05 - 0.5 * hist_vol**2) * safe_opts['time_to_exp_years']) / (hist_vol * np.sqrt(safe_opts['time_to_exp_years']))
                                                else:
                                                    safe_opts['d2'] = (np.log(safe_opts['breakeven'] / curr_price) + (0.05 - 0.5 * hist_vol**2) * safe_opts['time_to_exp_years']) / (hist_vol * np.sqrt(safe_opts['time_to_exp_years']))
                                                
                                                safe_opts['pop'] = norm.cdf(safe_opts['d2']) * 100
                                                
                                                profitable_opts = safe_opts[safe_opts['est_roi'] >= 0.25].copy()
                                                
                                                if profitable_opts.empty:
                                                    st.warning("⚠️ High Volatility: No options under $8.00 can mathematically guarantee 25% profit. Skip this trade.")
                                                else:
                                                    high_prob = profitable_opts.sort_values(by='pop', ascending=False).iloc[0]
                                                    
                                                    profitable_opts['dist_to_50'] = abs(profitable_opts['pop'] - 50.0)
                                                    balanced = profitable_opts.sort_values(by='dist_to_50', ascending=True).iloc[0]
                                                    
                                                    leverage = profitable_opts.sort_values(by='est_roi', ascending=False).iloc[0]
                                                    
                                                    st.success(f"**🛡️ Highest Probability of Profit**  \n"
                                                               f"Buy **${high_prob['strike']} {opt_type}** | Exp: {high_prob['expiration']}  \n"
                                                               f"**POP:** {high_prob['pop']:.1f}% chance of profit  \n"
                                                               f"*(Cost: ~${high_prob['effective_price']:.2f} | Est. Target ROI: +{(high_prob['est_roi']*100):.1f}%)*")
                                                    
                                                    st.info(f"**⚖️ Balanced Swing (~50% POP)**  \n"
                                                            f"Buy **${balanced['strike']} {opt_type}** | Exp: {balanced['expiration']}  \n"
                                                            f"**POP:** {balanced['pop']:.1f}% chance of profit  \n"
                                                            f"*(Cost: ~${balanced['effective_price']:.2f} | Est. Target ROI: +{(balanced['est_roi']*100):.1f}%)*")
                                                            
                                                    st.error(f"**🔥 Max Leverage (Lowest POP)**  \n"
                                                             f"Buy **${leverage['strike']} {opt_type}** | Exp: {leverage['expiration']}  \n"
                                                             f"**POP:** {leverage['pop']:.1f}% chance of profit  \n"
                                                             f"*(Cost: ~${leverage['effective_price']:.2f} | Est. Target ROI: +{(leverage['est_roi']*100):.1f}%)*")
                    else:
                        st.write("Trend is neutral. High-leverage option buys are not recommended right now.")

                st.divider()
                
                col_m1, col_m2, col_m3, col_m4 = st.columns(4)
                col_m1.metric("Market Price", f"${curr_price:.2f}")
                col_m2.metric("Daily Volume", vol_str)
                col_m3.metric("Shares Out", shares_str)
                col_m4.metric("Market Cap", cap_str)
                
                st.write("") 
                
                col_t1, col_t2, col_t3, col_t4 = st.columns(4)
                col_t1.metric("RSI (14)", f"{rsi_val:.1f}", rsi_reason, delta_color="off")
                col_t2.metric("MACD Line", f"{macd_val:.2f}", macd_reason, delta_color="off")
                col_t3.metric("Historical Vol", f"{hist_vol*100:.1f}%", delta_color="off")
                col_t4.metric("Avg 1-Wk Move", f"±${expected_1w_move:.2f}", delta_color="off")
                
                st.write("")
                
                col_s1, col_s2, col_s3 = st.columns(3)
                col_s1.metric("Macro Trend (NQ=F)", f"{nq_change_pct:.2f}%", futures_status, delta_color="normal")
                col_s2.metric("News Sentiment", f"{news_score}", news_sentiment_reason, delta_color="normal")
                col_s3.metric("Insider Action", f"{insider_score}", insider_sentiment_reason, delta_color="normal")
                
                st.divider()

                st.markdown("**Price Tracking**")
                st.line_chart(df[['Close', 'EMA_20', 'Support_20']], use_container_width=True)
                
                col_rsi, col_macd = st.columns(2)
                with col_rsi:
                    st.markdown("**RSI (14)**")
                    st.line_chart(df[['RSI', 'Overbought (70)', 'Oversold (30)']], use_container_width=True)
                with col_macd:
                    st.markdown("**MACD**")
                    st.line_chart(df[['MACD', 'Signal_Line']], use_container_width=True)
                    
                st.divider()
                
                with st.expander("📊 View Raw Price & Volume Data (Last 30 Days)"):
                    raw_df = df[['Close', 'Volume']].sort_index(ascending=False).head(30)
                    raw_df.index = raw_df.index.strftime('%Y-%m-%d')
                    st.dataframe(raw_df, use_container_width=True)
                    
                with st.expander("🕵️‍♂️ Insider Trading & Corporate News"):
                    col_ins, col_news = st.columns(2)
                    
                    with col_ins:
                        st.markdown("**Recent Insider / Hedge Fund Transactions**")
                        if insider_df is not None and not insider_df.empty:
                            st.dataframe(insider_df.head(15), use_container_width=True)
                        else:
                            st.info("No recent insider transactions found.")
                            
                    with col_news:
                        st.markdown("**Recent Buyback & Market News**")
                        if news:
                            found_news = False
                            for article in news:
                                title = article.get('title', '').lower()
                                if any(word in title for word in ['buyback', 'repurchase', 'insider', 'upgrade', 'downgrade', 'lawsuit']):
                                    pub_date = ""
                                    if 'providerPublishTime' in article:
                                        pub_date = datetime.fromtimestamp(article['providerPublishTime']).strftime('%Y-%m-%d') + " - "
                                    st.write(f"- {pub_date}[{article['title']}]({article['link']})")
                                    found_news = True
                            if not found_news:
                                st.write("*No recent news articles specifically mentioning major catalysts or insider activity.*")
                        else:
                            st.info("News feed not currently available.")