import streamlit as st
import json
import streamlit.components.v1 as components
import re  # ★★★★★ 修正点: 正規表現モジュールを追加

# --- StreamlitアプリケーションのUI ---

st.set_page_config(layout="wide", page_title="Mermaid Editor")

st.title("🧜‍♀️ Mermaid記法 システム図ジェネレーター (スタンドアロン版)")
st.write(
    "左側のテキストエリアにMermaid記法でシステム図の定義を入力してください。"
    "右側に図がリアルタイムで表示され、PNG形式でダウンロードできます。"
)
st.info("ℹ️ このアプリは外部サービスを利用せず、お使いのブラウザ内ですべての処理を実行します。")

# サンプル用のMermaidコード
# []の中に()があるケース（エラーになりやすい例）を含めています
DEFAULT_MERMAID_CODE = """
graph TD
    A[クライアント] --> B{ロードバランサー};
    B --> C[Webサーバー1];
    B --> D[Webサーバー2];
    C --> E(データベース);
    D --> E(データベース);
    E --> F[データ分析基盤(BigQuery)];
    F --> G[レポート(日次)];
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
    <!-- Mermaid.jsライブラリをCDNから読み込み -->
    <script src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"></script>
    <style>
        body {
            font-family: sans-serif;
            color: __FONT_COLOR__; /* Streamlitのテーマに合わせる */
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
        // Pythonから渡されたMermaidコードとテーマ設定
        const mermaidCode = __MERMAID_CODE_JSON__;
        const theme = '__THEME__';
        
        // Mermaid.jsの初期化
        mermaid.initialize({ startOnLoad: false, theme: theme });

        const renderMermaid = async () => {
            const container = document.getElementById('mermaid-container');
            
            try {
                // Mermaidコードをコンテナに挿入して実行
                container.innerHTML = mermaidCode;
                await mermaid.run({ nodes: [container] });
            } catch (e) {
                container.innerHTML = `<pre style="color:red;"><b>Error:</b>\\n${e.message}</pre>`;
            }
        };

        // PNGダウンロードボタンの処理
        document.getElementById('download-btn').onclick = () => {
            const svgElement = document.querySelector('#mermaid-container svg');
            if (!svgElement) {
                alert('Diagram not rendered yet.');
                return;
            }

            const canvas = document.getElementById('canvas');
            const ctx = canvas.getContext('2d');
            const padding = 20; // 余白

            const svgWidth = svgElement.clientWidth;
            const svgHeight = svgElement.clientHeight;

            canvas.width = svgWidth + padding * 2;
            canvas.height = svgHeight + padding * 2;
            
            ctx.fillStyle = 'white'; // 背景を白で塗りつぶす
            ctx.fillRect(0, 0, canvas.width, canvas.height);

            const svgData = new XMLSerializer().serializeToString(svgElement);
            const svgUrl = 'data:image/svg+xml;charset=utf-8;base64,' + btoa(unescape(encodeURIComponent(svgData)));
            
            const img = new Image();
            img.onload = () => {
                ctx.drawImage(img, padding, padding, svgWidth, svgHeight);
                const pngUrl = canvas.toDataURL('image/png');
                
                // ダウンロード用のリンクを動的に作成してクリック
                const a = document.createElement('a');
                a.href = pngUrl;
                a.download = 'system_diagram.png';
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
            };
            img.src = svgUrl;
        };

        // ページ読み込み時にMermaidを描画
        renderMermaid();
    </script>
</body>
</html>
"""

# ★★★★★ 追加機能: []内の()を処理する関数 ★★★★★
def sanitize_mermaid_brackets(code):
    """
    Mermaidコード内で [] の中に () が含まれている場合、
    その文字列全体を "" で囲むように置換します。
    例: A[Func(x)] -> A["Func(x)"]
    """
    def replace_brackets(match):
        content = match.group(1) # []の中身
        # 中身に ( または ) が含まれているかチェック
        if '(' in content or ')' in content:
            # 既にダブルクォートで囲まれている場合は何もしない
            stripped = content.strip()
            if stripped.startswith('"') and stripped.endswith('"'):
                return f'[{content}]'
            # ダブルクォートで囲んで返す
            return f'["{content}"]'
        
        # ()が含まれていなければそのまま
        return f'[{content}]'

    # 正規表現で [任意の文字] を検索して置換関数を適用
    # \[ : [のエスケープ
    # ([^\]]+) : ]以外の文字が1文字以上続く（グループ1としてキャプチャ）
    # \] : ]のエスケープ
    return re.sub(r'\[([^\]]+)\]', replace_brackets, code)


with col2:
    st.subheader("システム図プレビュー")
    
    if mermaid_code:
        # ★★★★★ 修正点: 入力されたコードをサニタイズ（自動補正） ★★★★★
        processed_code = sanitize_mermaid_brackets(mermaid_code)

        # Streamlitの現在のテーマ（light/dark）を取得
        st_theme = st.get_option("theme.base")
        mermaid_theme = "dark" if st_theme == "dark" else "default"
        font_color = "white" if st_theme == "dark" else "black"

        html_code = MERMAID_TEMPLATE.replace(
            "__MERMAID_CODE_JSON__", json.dumps(processed_code) # 補正後のコードを使用
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