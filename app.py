import streamlit as st
import json
import streamlit.components.v1 as components
import re

# --- StreamlitアプリケーションのUI ---

st.set_page_config(layout="wide", page_title="Mermaid Editor")

st.title("🧜‍♀️ Mermaid記法 システム図ジェネレーター (スタンドアロン版)")
st.write(
    "左側のテキストエリアにMermaid記法でシステム図の定義を入力してください。"
    "右側に図がリアルタイムで表示され、PNG形式でダウンロードできます。"
)
st.info("ℹ️ このアプリは外部サービスを利用せず、お使いのブラウザ内ですべての処理を実行します。")

# サンプル用のMermaidコード
# []の中に{}があるケース（subgraphラベルでのエラー例）
DEFAULT_MERMAID_CODE = """
graph TD
    subgraph Client [クライアントアプリ]
        U[User] --> F[Frontend];
    end

    %% ご指摘のケース: {}が含まれるサブグラフラベル
    subgraph FileSystem [Local Storage /data/{user_id}/]
        D1[(UserConfig)];
        D2[(SessionData)];
    end
    
    F --> FileSystem;
    F --> API[API Server];
    API -->|"検索クエリ(JSON)"| DB[(Database)];
"""

# 画面を2カラムに分割
col1, col2 = st.columns(2)

with col1:
    st.subheader("Mermaid記法入力")
    mermaid_code = st.text_area(
        "ここにMermaidコードを入力",
        value=DEFAULT_MERMAID_CODE,
        height=600,
        label_visibility="collapsed"
    )

# --- HTML/JavaScriptでMermaidを描画・ダウンロードする部分 ---

MERMAID_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Mermaid Renderer</title>
    <script src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"></script>
    <style>
        body {
            font-family: sans-serif;
            color: __FONT_COLOR__; 
            margin: 0;
            padding: 1rem;
        }
        #download-btn {
            display: inline-block;
            padding: 8px 16px;
            border: 1px solid #ccc;
            border-radius: 4px;
            cursor: pointer;
            background-color: #f0f2f6;
            color: #333;
            margin-bottom: 1rem;
            text-decoration: none;
        }
        #download-btn:hover {
            background-color: #e0e2e6;
        }
        #mermaid-container {
            text-align: center;
        }
    </style>
</head>
<body>
    <button id="download-btn">Download as PNG</button>
    <div id="mermaid-container"></div>
    <canvas id="canvas" style="display:none;"></canvas>

    <script>
        const mermaidCode = __MERMAID_CODE_JSON__;
        const theme = '__THEME__';
        mermaid.initialize({ startOnLoad: false, theme: theme });

        const renderMermaid = async () => {
            const container = document.getElementById('mermaid-container');
            try {
                container.innerHTML = mermaidCode;
                await mermaid.run({ nodes: [container] });
            } catch (e) {
                container.innerHTML = `<pre style="color:red;"><b>Error:</b>\\n${e.message}</pre>`;
            }
        };

        document.getElementById('download-btn').onclick = () => {
            const svgElement = document.querySelector('#mermaid-container svg');
            if (!svgElement) {
                alert('Diagram not rendered yet.');
                return;
            }
            const canvas = document.getElementById('canvas');
            const ctx = canvas.getContext('2d');
            const padding = 20;
            const svgWidth = svgElement.clientWidth;
            const svgHeight = svgElement.clientHeight;

            canvas.width = svgWidth + padding * 2;
            canvas.height = svgHeight + padding * 2;
            
            ctx.fillStyle = 'white';
            ctx.fillRect(0, 0, canvas.width, canvas.height);

            const svgData = new XMLSerializer().serializeToString(svgElement);
            const svgUrl = 'data:image/svg+xml;charset=utf-8;base64,' + btoa(unescape(encodeURIComponent(svgData)));
            
            const img = new Image();
            img.onload = () => {
                ctx.drawImage(img, padding, padding, svgWidth, svgHeight);
                const pngUrl = canvas.toDataURL('image/png');
                const a = document.createElement('a');
                a.href = pngUrl;
                a.download = 'system_diagram.png';
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
            };
            img.src = svgUrl;
        };
        renderMermaid();
    </script>
</body>
</html>
"""

# ★★★★★ 修正機能: []内の()や{}を処理する関数 ★★★★★
def sanitize_mermaid_code(code):
    """
    Mermaidコード内の特殊文字によるエラーを回避するための自動修正。
    [] や || の中に (), {} が含まれている場合、"" で囲む処理を行います。
    """
    
    # --- 1. ノード/サブグラフラベル [...] の修正処理 ---
    def replace_node_brackets(match):
        content = match.group(1)
        
        # ケース1: 円筒形記法 [(...)] -> [("...")]
        # これは例外的に外側の()を残す必要がある
        if content.startswith('(') and content.endswith(')'):
            inner = content[1:-1]
            stripped_inner = inner.strip()
            if stripped_inner.startswith('"') and stripped_inner.endswith('"'):
                return f'[{content}]'
            return f'[("{inner}")]'
        
        # ケース2: 通常ノード/サブグラフ [...] -> ["..."]
        else:
            # エラーの原因となる文字が含まれているかチェック
            # () : 丸括弧（通常のノード記法と競合）
            # {} : 波括弧（ひし形ノード記法と競合）
            check_chars = ['(', ')', '{', '}']
            
            if any(char in content for char in check_chars):
                stripped = content.strip()
                # 既にダブルクォートで囲まれている場合は何もしない
                if stripped.startswith('"') and stripped.endswith('"'):
                    return f'[{content}]'
                # ダブルクォートで囲む
                return f'["{content}"]'
            
            return f'[{content}]'

    # --- 2. リンクテキスト |...| の修正処理 ---
    def replace_link_label(match):
        content = match.group(1) # |...| の中身
        
        # リンクテキストも同様に (), {} があればクォートする
        check_chars = ['(', ')', '{', '}']
        
        if any(char in content for char in check_chars):
            stripped = content.strip()
            if stripped.startswith('"') and stripped.endswith('"'):
                return f'|{content}|'
            return f'|"{content}"|'
        
        return f'|{content}|'

    # 正規表現の適用
    # Step 1: ノード/サブグラフ [...] の修正
    code = re.sub(r'\[([^\]]+)\]', replace_node_brackets, code)
    
    # Step 2: リンクテキスト |...| の修正
    code = re.sub(r'\|([^|]+)\|', replace_link_label, code)
    
    return code


with col2:
    st.subheader("システム図プレビュー")
    
    if mermaid_code:
        # 入力されたコードをサニタイズ
        processed_code = sanitize_mermaid_code(mermaid_code)

        st_theme = st.get_option("theme.base")
        mermaid_theme = "dark" if st_theme == "dark" else "default"
        font_color = "white" if st_theme == "dark" else "black"

        html_code = MERMAID_TEMPLATE.replace(
            "__MERMAID_CODE_JSON__", json.dumps(processed_code)
        ).replace(
            "__THEME__", mermaid_theme
        ).replace(
            "__FONT_COLOR__", font_color
        )
        
        components.html(html_code, height=620, scrolling=True)
    else:
        st.warning("左側のエリアにMermaidコードを入力してください。")


st.markdown("---")
st.markdown("### Mermaid記法について")
st.info(
    "Mermaidは、Markdownに似たテキストベースの記法でフローチャート、シーケンス図、ガントチャートなどを簡単に作成できるツールです。\n"
    "記法の詳細は[公式ドキュメント](https://mermaid.js.org/intro/)をご参照ください。"
)