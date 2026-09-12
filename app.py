import streamlit as st
import os
import time
from pathlib import Path
from main import process_url, is_valid_url
from scrape_sitemap import extract_urls_from_sitemap

st.set_page_config(page_title="Web Scraper", page_icon="🕸️", layout="wide")

st.title("🕸️ Web Scraper")

# Sidebar for settings
with st.sidebar:
    st.header("⚙️ Settings")
    output_dir = st.text_input("Output Directory", value="output")
    limit = st.number_input("Max URLs to Scrape (0 = Unlimited)", min_value=0, value=0)
    st.markdown("---")
    st.markdown("Built with [Streamlit](https://streamlit.io)")

# Ensure output dir exists
os.makedirs(output_dir, exist_ok=True)

# Main layout using tabs
tab1, tab2, tab3 = st.tabs(["Single URL", "Multiple URLs", "Sitemap"])

# --- TAB 1: Single URL ---
with tab1:
    st.subheader("Scrape a Single URL")
    url_input = st.text_input("Enter Webpage URL:", placeholder="https://example.com/article")
    
    if st.button("Scrape URL", type="primary", key="btn_single"):
        if not url_input or not is_valid_url(url_input):
            st.error("Please enter a valid URL.")
        else:
            with st.spinner("Scraping..."):
                result = process_url(url_input, output_dir)
                if "error" in result:
                    st.error(f"Error: {result['error']}")
                else:
                    st.success(f"Successfully scraped: {result['title']}")
                    with st.expander("View Extracted Markdown"):
                        st.markdown(result['content'])

# --- TAB 2: Multiple URLs ---
with tab2:
    st.subheader("Scrape Multiple URLs")
    st.markdown("Enter URLs (one per line) or upload a `.txt` file.")
    
    col1, col2 = st.columns(2)
    with col1:
        urls_text = st.text_area("URLs List", height=200, placeholder="https://example.com/1\nhttps://example.com/2")
    with col2:
        uploaded_file = st.file_uploader("Upload URLs File", type=["txt"])
    
    if st.button("Scrape URLs", type="primary", key="btn_multi"):
        urls = []
        if uploaded_file is not None:
            content = uploaded_file.getvalue().decode("utf-8")
            urls.extend([line.strip() for line in content.split("\n") if line.strip() and not line.startswith("#")])
        if urls_text:
            urls.extend([line.strip() for line in urls_text.split("\n") if line.strip() and not line.startswith("#")])
        
        valid_urls = [u for u in set(urls) if is_valid_url(u)]
        
        if not valid_urls:
            st.warning("No valid URLs found.")
        else:
            if limit > 0:
                valid_urls = valid_urls[:limit]
                st.info(f"Limiting to first {limit} URLs.")
            
            progress_text = "Operation in progress. Please wait."
            my_bar = st.progress(0, text=progress_text)
            
            results = []
            for i, u in enumerate(valid_urls):
                my_bar.progress((i) / len(valid_urls), text=f"Scraping ({i+1}/{len(valid_urls)}): {u}")
                res = process_url(u, output_dir)
                results.append(res)
                
            my_bar.progress(1.0, text="Scraping complete!")
            
            success_count = sum(1 for r in results if "error" not in r)
            st.success(f"Job completed. Successfully scraped {success_count}/{len(valid_urls)} URLs.")
            
            if success_count > 0:
                st.subheader("Scraping Results")
                for res in results:
                    if "error" not in res:
                        with st.expander(f"📄 {res['title']}"):
                            st.markdown(f"**URL:** {res['url']}")
                            st.markdown(res['content'])

# --- TAB 3: Sitemap ---
with tab3:
    st.subheader("Extract & Scrape from Sitemap")
    sitemap_url = st.text_input("Enter Sitemap XML URL:", placeholder="https://example.com/sitemap.xml")
    
    if st.button("Extract URLs & Scrape", type="primary", key="btn_sitemap"):
        if not sitemap_url or not is_valid_url(sitemap_url):
            st.error("Please enter a valid Sitemap URL.")
        else:
            with st.spinner("Extracting URLs from sitemap..."):
                extracted_urls = extract_urls_from_sitemap(sitemap_url)
                unique_urls = list(dict.fromkeys(extracted_urls)) # preserve order, remove duplicates
            
            if not unique_urls:
                st.warning("No URLs found in the sitemap.")
            else:
                st.info(f"Found {len(unique_urls)} unique URLs.")
                if limit > 0:
                    unique_urls = unique_urls[:limit]
                    st.info(f"Limiting to first {limit} URLs.")
                
                my_bar = st.progress(0, text="Starting scrape...")
                results = []
                for i, u in enumerate(unique_urls):
                    my_bar.progress((i) / len(unique_urls), text=f"Scraping ({i+1}/{len(unique_urls)}): {u}")
                    res = process_url(u, output_dir)
                    results.append(res)
                    
                my_bar.progress(1.0, text="Scraping complete!")
                success_count = sum(1 for r in results if "error" not in r)
                st.success(f"Job completed. Successfully scraped {success_count}/{len(unique_urls)} URLs.")
                
                if success_count > 0:
                    st.subheader("Scraping Results")
                    for res in results:
                        if "error" not in res:
                            with st.expander(f"📄 {res['title']}"):
                                st.markdown(f"**URL:** {res['url']}")
                                st.markdown(res['content'])
