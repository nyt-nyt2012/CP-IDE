/* ==========================================================================
   CP-IDE — Markdown 扩展渲染器

   在 CommonMark / GFM 的基础上，补齐洛谷 Markdown 手册里的扩展语法：

   * :::align{center} / :::align{right}   居中 / 居右排版
   * :::epigraph[——otto]                 引言
   * :::info[标题] / success / warning / error   折叠框（支持 {open} 默认展开）
   * 折叠框可嵌套（最内层三个 :，每往外一层加一个 :）
   * ::cute-table{tuack}                  更像 Tuack 的表格
   * 表格单元格合并：^ 向上合并、< 向左合并
   * 代码块右上角「复制」按钮
   * 代码块语法高亮（CodeMirror runmode，本地内置）
   * 代码块行号：```cpp line-numbers
   * 行末单个反斜杠也算换行
   * 裸网址自动转成链接
   * 用图片语法写 B 站链接时，渲染成内嵌播放器
   * 行内 / 行间 LaTeX 公式（KaTeX）

   公式、代码块、容器都是**先摘出来**再交给 Markdown 解析器的，
   否则 Markdown 会把 LaTeX 里的 \\ 之类吃掉。
   ========================================================================== */
(function () {
    'use strict';

    const TOKEN_PREFIX = '%%CP';
    const TOKEN_SUFFIX = '%%';

    /* ------------------------------ 工具 ------------------------------ */

    function escapeHtml(text) {
        return String(text == null ? '' : text)
            .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    function token(index) {
        return TOKEN_PREFIX + index + TOKEN_SUFFIX;
    }

    function isFence(line) {
        return /^\s{0,3}(`{3,}|~{3,})/.test(line);
    }

    /* 围栏信息串里可以写的「开关」 */
    const FENCE_ATTR_WORDS = [
        'line-numbers', 'linenumbers', 'line-number', 'numberlines', 'numbers',
        'showlinenumbers', 'show-line-numbers', 'nowrap', 'no-wrap',
        'nohl', 'nohighlight', 'title', 'caption'
    ];

    /* 解析围栏后面的信息串，返回 { lang, attrs }
       支持的写法：
         ```cpp
         ```cpp line-numbers
         ```cpp {line-numbers}
         ```{cpp line-numbers}
         ```{.cpp .line-numbers}
       语言名后面跟的词会被当成开关（当前支持 line-numbers 行号）。 */
    function parseFenceInfo(info) {
        const raw = String(info == null ? '' : info);
        const tokens = [];
        /* 先把 {...} 里的内容拆出来，剩下的按空白 / 逗号切 */
        const rest = raw.replace(/\{([^}]*)\}/g, function (m, body) {
            body.split(/[\s,]+/).forEach(function (t) { if (t) tokens.push(t); });
            return ' ';
        });
        rest.split(/[\s,]+/).forEach(function (t) { if (t) tokens.push(t); });

        let lang = '';
        const attrs = [];
        tokens.forEach(function (item) {
            const t = item.replace(/^\./, '').toLowerCase();
            if (!t) return;
            if (FENCE_ATTR_WORDS.indexOf(t) >= 0 || t.indexOf('=') >= 0) {
                attrs.push(t);
                return;
            }
            if (!lang) { lang = t; return; }
            attrs.push(t);
        });
        return { lang: lang, attrs: attrs };
    }

    /* 是否要求显示行号 */
    function wantsLineNumbers(attrs) {
        return (attrs || []).some(function (a) {
            return a === 'line-numbers' || a === 'linenumbers' || a === 'line-number' ||
                a === 'numberlines' || a === 'numbers' ||
                a === 'showlinenumbers' || a === 'show-line-numbers';
        });
    }

    /* 行内公式的判断：$ 后面不能是空格，结尾 $ 前面不能是空格 */
    function looksLikeInlineMath(text) {
        return /(^|[^\\$])\$(?!\s)((?:\\.|[^\\$\n])+?)(?<!\s)\$(?!\d)/.test(text);
    }

    /* --------------------------- 各类内容提取 --------------------------- */

    /* 围栏代码块
       信息串可以是「语言 + 开关」，例如 ```cpp line-numbers。
       以前这里只认单个词的语言名，遇到带开关的围栏就会把「结束围栏」
       当成「开始围栏」，导致后面整段正文被当成代码块（并挂上 text 标签）。 */
    function extractCodeBlocks(text, store) {
        const lines = text.split('\n');
        const out = [];
        let i = 0;
        while (i < lines.length) {
            const line = lines[i];
            const m = /^\s{0,3}(`{3,}|~{3,})[ \t]*(.*?)[ \t]*$/.exec(line);
            if (m) {
                const fence = m[1];
                const marker = fence.charAt(0);
                const closeRe = new RegExp('^\\s{0,3}' + (marker === '`' ? '`' : '~') +
                    '{' + fence.length + ',}[ \\t]*$');
                let j = i + 1;
                while (j < lines.length && !closeRe.test(lines[j])) j += 1;
                if (j >= lines.length) {
                    /* 没有闭合围栏 → 当成普通文本，不吞掉后面的正文 */
                    out.push(line);
                    i += 1;
                    continue;
                }
                const info = parseFenceInfo(m[2]);
                store.push({
                    kind: 'code',
                    lang: info.lang,
                    attrs: info.attrs,
                    body: lines.slice(i + 1, j).join('\n')
                });
                out.push('', token(store.length - 1), '');
                i = j + 1;
                continue;
            }
            out.push(line);
            i += 1;
        }
        return out.join('\n');
    }

    /* 行间公式 $$...$$ 与 \[...\] */
    function extractBlockMath(text, store) {
        let result = text.replace(/\$\$([\s\S]+?)\$\$/g, function (m, body) {
            store.push({ kind: 'math', display: true, body: body });
            return '\n\n' + token(store.length - 1) + '\n\n';
        });
        result = result.replace(/\\\[([\s\S]+?)\\\]/g, function (m, body) {
            store.push({ kind: 'math', display: true, body: body });
            return '\n\n' + token(store.length - 1) + '\n\n';
        });
        return result;
    }

    /* 行内公式 $...$ */
    function extractInlineMath(text, store) {
        return text.replace(/(^|[^\\$])\$(?!\s)((?:\\.|[^\\$\n])+?)(?<!\s)\$(?!\$)/g, function (m, pre, body) {
            if (!body.trim()) return m;
            store.push({ kind: 'math', display: false, body: body });
            return pre + token(store.length - 1);
        });
    }

    /* 行内代码 */
    function extractInlineCode(text, store) {
        return text.replace(/(`+)([^`]|[^`][\s\S]*?[^`])\1(?!`)/g, function (m, ticks, body) {
            store.push({ kind: 'inline-code', body: body });
            return token(store.length - 1);
        });
    }

    /* ::: 容器：找出最内层的一对，先摘出来（可重复） */
    function extractContainers(text, store) {
        const lines = text.split('\n');
        const marker = /^(:{3,})([a-zA-Z][\w-]*)?(\[[^\]]*\])?(\{[^}]*\})?\s*$/;

        const infos = lines.map(function (line) {
            const m = marker.exec(line);
            if (!m) return null;
            return {
                colons: m[1].length,
                name: (m[2] || '').toLowerCase(),
                title: m[3] ? m[3].slice(1, -1) : '',
                params: m[4] ? m[4].slice(1, -1) : '',
                hasTitle: !!m[3],
                hasParams: !!m[4]
            };
        });

        let changed = true;
        while (changed) {
            changed = false;
            for (let i = 0; i < infos.length; i += 1) {
                const open = infos[i];
                if (!open || !open.name) continue;
                // 找同层数的结束标记（无名字），中间不能有同层数的标记
                for (let j = i + 1; j < infos.length; j += 1) {
                    const close = infos[j];
                    if (!close) continue;
                    if (close.colons === open.colons) {
                        if (close.name) break;          // 同层但带名字 → 不是结束标记
                        // 找到一对
                        store.push({
                            kind: 'container',
                            name: open.name,
                            title: open.title,
                            params: open.params,
                            hasTitle: open.hasTitle,
                            hasParams: open.hasParams,
                            content: lines.slice(i + 1, j).join('\n')
                        });
                        const placeholder = token(store.length - 1);
                        const newLines = lines.slice(0, i).concat(['', placeholder, ''], lines.slice(j + 1));
                        lines.length = 0;
                        Array.prototype.push.apply(lines, newLines);
                        infos.length = 0;
                        Array.prototype.push.apply(infos, newLines.map(function (line) {
                            const m = marker.exec(line);
                            if (!m) return null;
                            return {
                                colons: m[1].length,
                                name: (m[2] || '').toLowerCase(),
                                title: m[3] ? m[3].slice(1, -1) : '',
                                params: m[4] ? m[4].slice(1, -1) : '',
                                hasTitle: !!m[3],
                                hasParams: !!m[4]
                            };
                        }));
                        changed = true;
                        break;
                    }
                    if (close.colons < open.colons) break;  // 外层容器的结束标记
                }
            }
        }
        return lines.join('\n');
    }

    /* 裸网址自动转链接
       注意别去动 Markdown 自己的链接/图片目标（](...)）和引用式链接的定义行。 */
    function autoLink(text) {
        const lines = text.split('\n');
        for (let i = 0; i < lines.length; i += 1) {
            if (/^\s{0,3}\[[^\]]+\]:\s*\S+/.test(lines[i])) continue;   // 引用式链接定义
            lines[i] = lines[i].replace(
                /(^|[\s(（])(https?:\/\/[^\s<>"'）)]+)/g,
                function (match, pre, url, offset, whole) {
                    const before = whole.slice(0, offset);
                    if (before.charAt(before.length - 1) === ']') return match;  // 是 ](目标)
                    return pre + '[' + url + '](' + url + ')';
                }
            );
        }
        return lines.join('\n');
    }

    /* 行末单个反斜杠 → 两个空格（Markdown 的硬换行） */
    function backslashBreaks(text) {
        return text.replace(/(^|[^\\])\\$/gm, '$1  ');
    }

    /* ------------------------------ 渲染 ------------------------------ */

    function renderMath(body, display) {
        if (!window.katex || !window.katex.renderToString) {
            return '<code class="md-math-error">' + escapeHtml(body) + '</code>';
        }
        try {
            return window.katex.renderToString(String(body || ''), {
                displayMode: !!display,
                throwOnError: false,
                output: 'htmlAndMathml'
            });
        } catch (err) {
            return '<code class="md-math-error">' + escapeHtml(body) + '</code>';
        }
    }

    /* 容器 → HTML */
    function renderContainer(item, innerHtml) {
        const name = item.name;
        const title = item.title || '';
        const params = item.params || '';

        if (name === 'align') {
            const align = (params || 'center').toLowerCase();
            const cls = align === 'right' ? 'md-align-right' : 'md-align-center';
            return '<div class="' + cls + '">' + innerHtml + '</div>';
        }
        if (name === 'epigraph') {
            const author = title ? '<div class="md-epigraph-author">' + renderTitle(title) + '</div>' : '';
            return '<blockquote class="md-epigraph">' + innerHtml + author + '</blockquote>';
        }
        if (['info', 'success', 'warning', 'error', 'tip', 'note'].indexOf(name) >= 0) {
            const labels = {
                info: '提示', success: '成功', warning: '警告',
                error: '错误', tip: '提示', note: '说明'
            };
            const open = /(^|,)\s*open\s*(,|$)/.test(params) ? ' open' : '';
            const head = title ? renderTitle(title) : escapeHtml(labels[name] || '提示');
            return '<details class="md-callout md-callout-' + name + '"' + open + '>' +
                '<summary class="md-callout-title">' + head + '</summary>' +
                '<div class="md-callout-body">' + innerHtml + '</div>' +
                '</details>';
        }
        // 未知容器：原样保留内容
        return innerHtml;
    }

    /* 标题：允许其中夹带 Markdown 与 LaTeX 公式 */
    function renderTitle(title) {
        const html = toHtml(String(title || ''), []);
        return html.replace(/^<p>/, '').replace(/<\/p>\s*$/, '');
    }

    /* 代码块 → HTML（语法高亮与行号在 DOM 后处理阶段补上） */
    function renderCodeBlock(item) {
        return '<pre class="md-code" data-md-lang="' + escapeHtml(item.lang || '') +
            '" data-md-attrs="' + escapeHtml((item.attrs || []).join(' ')) +
            '"><code class="language-' + escapeHtml(item.lang || 'text') +
            '">' + escapeHtml(item.body) + '</code></pre>';
    }

    /* 主渲染：Markdown 文本 → HTML 字符串
       store 贯穿整个递归过程：容器内容里可能还留有外层提取出的占位符，
       必须用同一个 store 才能还原。

       提取顺序很重要：**先摘容器**，否则容器标题里的 $$公式$$ 会被
       拆成多行，容器就识别不出来了。 */
    function toHtml(source, store) {
        if (!store) store = [];
        let text = String(source == null ? '' : source);

        text = extractContainers(text, store);
        text = extractCodeBlocks(text, store);
        text = extractBlockMath(text, store);
        text = extractInlineMath(text, store);
        text = extractInlineCode(text, store);
        text = autoLink(text);
        text = backslashBreaks(text);

        let html;
        try {
            html = (window.marked && window.marked.parse)
                ? window.marked.parse(text, { gfm: true, breaks: false })
                : '<pre>' + escapeHtml(source) + '</pre>';
        } catch (err) {
            html = '<pre>' + escapeHtml(source) + '</pre>';
        }

        /* 代码块占位符外面通常会裹一层 <p>，直接连着 <pre> 会多出空段落 */
        html = html.replace(/<p>\s*(%%CP\d+%%)\s*<\/p>/g, function (match, tk) {
            const m = /%%CP(\d+)%%/.exec(tk);
            const item = m ? store[Number(m[1])] : null;
            if (!item || item.kind !== 'code') return match;
            return renderCodeBlock(item);
        });

        // 还原占位符
        const pattern = new RegExp(TOKEN_PREFIX + '(\\d+)' + TOKEN_SUFFIX, 'g');
        html = html.replace(pattern, function (match, index) {
            const item = store[Number(index)];
            if (!item) return match;
            if (item.kind === 'math') return renderMath(item.body, item.display);
            if (item.kind === 'inline-code') return '<code>' + escapeHtml(item.body) + '</code>';
            if (item.kind === 'code') return renderCodeBlock(item);
            if (item.kind === 'container') {
                return renderContainer(item, toHtml(item.content, store));
            }
            return match;
        });

        return html;
    }

    /* ------------------------- DOM 后处理（表格等） ------------------------- */

    /* 表格单元格合并：^ 向上、< 向左
       先把表格摊成网格，算出每个单元格的行列位置，再决定合并关系。 */
    function mergeTableCells(table) {
        const matrix = [];
        Array.prototype.slice.call(table.rows).forEach(function (tr, r) {
            const cells = [];
            Array.prototype.slice.call(tr.cells).forEach(function (td) {
                cells.push({
                    node: td,
                    text: (td.textContent || '').trim(),
                    colspan: parseInt(td.getAttribute('colspan') || '1', 10),
                    rowspan: parseInt(td.getAttribute('rowspan') || '1', 10),
                    row: r,
                    col: -1,
                    removed: false
                });
            });
            matrix.push(cells);
        });

        // 计算每个单元格占据的起始列
        const occupied = [];
        matrix.forEach(function (cells, r) {
            occupied[r] = occupied[r] || [];
            let c = 0;
            cells.forEach(function (cell) {
                while (occupied[r][c]) { c += 1; }
                cell.col = c;
                for (let dr = 0; dr < cell.rowspan; dr += 1) {
                    occupied[r + dr] = occupied[r + dr] || [];
                    for (let dc = 0; dc < cell.colspan; dc += 1) {
                        occupied[r + dr][c + dc] = true;
                    }
                }
                c += cell.colspan;
            });
        });

        // 处理 ^ 与 <
        matrix.forEach(function (cells, r) {
            cells.forEach(function (cell) {
                if (cell.text === '^') {
                    const above = cellAtColumn(matrix, r - 1, cell.col);
                    if (above) {
                        if (above.row + above.rowspan <= r) {
                            above.rowspan += 1;
                        }
                        cell.removed = true;
                    }
                } else if (cell.text === '<') {
                    const left = cellLeftOf(matrix, r, cell.col);
                    if (left) {
                        left.colspan += 1;
                        cell.removed = true;
                    }
                }
            });
        });

        // 应用结果
        matrix.forEach(function (cells) {
            cells.forEach(function (cell) {
                if (cell.removed) {
                    if (cell.node.parentNode) cell.node.parentNode.removeChild(cell.node);
                    return;
                }
                if (cell.rowspan > 1) cell.node.setAttribute('rowspan', String(cell.rowspan));
                if (cell.colspan > 1) cell.node.setAttribute('colspan', String(cell.colspan));
            });
        });
    }

    /* 找到第 row 行、col 列位置上被占用的单元格 */
    function cellAtColumn(matrix, row, col) {
        if (row < 0) return null;
        const cells = matrix[row] || [];
        for (let i = 0; i < cells.length; i += 1) {
            const cell = cells[i];
            if (cell.removed) continue;
            if (col >= cell.col && col < cell.col + cell.colspan) return cell;
        }
        return null;
    }

    /* 找到同一行里紧邻左侧的单元格 */
    function cellLeftOf(matrix, row, col) {
        const cells = matrix[row] || [];
        let best = null;
        for (let i = 0; i < cells.length; i += 1) {
            const cell = cells[i];
            if (cell.removed) continue;
            if (cell.col <= col - 1 && cell.col + cell.colspan > col - 1) {
                if (!best || cell.col > best.col) best = cell;
            }
        }
        return best;
    }

    /* ---------------------------- 代码块 ---------------------------- */

    /* 语言 → CodeMirror 模式（全部本地内置，完全离线） */
    const LANG_MODES = {
        'cpp': 'text/x-c++src', 'c++': 'text/x-c++src', 'cc': 'text/x-c++src',
        'cxx': 'text/x-c++src', 'hpp': 'text/x-c++src', 'hh': 'text/x-c++src',
        'h': 'text/x-c++src', 'c++11': 'text/x-c++src', 'c++14': 'text/x-c++src',
        'c++17': 'text/x-c++src', 'c++20': 'text/x-c++src',
        'c': 'text/x-csrc', 'chdr': 'text/x-chdr',
        'python': 'text/x-python', 'py': 'text/x-python', 'python3': 'text/x-python',
        'java': 'text/x-java', 'kotlin': 'text/x-kotlin', 'kt': 'text/x-kotlin',
        'csharp': 'text/x-csharp', 'cs': 'text/x-csharp',
        'scala': 'text/x-scala', 'objectivec': 'text/x-objectivec', 'objc': 'text/x-objectivec',
        'ceylon': 'text/x-ceylon', 'squirrel': 'text/x-squirrel', 'nesc': 'text/x-nesc',
        'xml': 'application/xml', 'html': 'application/xml', 'svg': 'application/xml',
        'markdown': 'text/x-markdown', 'md': 'text/x-markdown'
    };

    /* 用 CodeMirror 的 runmode 插件做语法高亮 */
    function highlightCode(codeEl, lang) {
        if (!window.CodeMirror || typeof window.CodeMirror.runMode !== 'function') return false;
        const mode = LANG_MODES[lang];
        if (!mode) return false;
        const raw = codeEl.textContent || '';
        try {
            window.CodeMirror.runMode(raw, mode, codeEl);
            return true;
        } catch (err) {
            return false;
        }
    }

    /* 代码块：语言标签 + 复制按钮 + 语法高亮 + 行号 */
    function decorateCodeBlocks(container, options) {
        const opts = options || {};
        const blocks = Array.prototype.slice.call(container.querySelectorAll('pre'));
        blocks.forEach(function (pre) {
            const code = pre.querySelector('code');
            if (!code) return;
            if (pre.getAttribute('data-md-ready') === '1') return;
            pre.setAttribute('data-md-ready', '1');

            let lang = (code.getAttribute('data-md-lang') || '').toLowerCase();
            if (!lang) {
                const m = /language-([\w+#.-]+)/.exec(code.className || '');
                if (m) lang = m[1].toLowerCase();
            }
            const attrs = (code.getAttribute('data-md-attrs') || '').split(/[\s,]+/).filter(Boolean);
            const raw = code.textContent || '';

            /* 语法高亮 */
            if (opts.highlight !== false && highlightCode(code, lang)) {
                code.classList.add('cm-code');
            }

            /* 行号：围栏里写了 line-numbers，或者全局开关打开 */
            const withNumbers = wantsLineNumbers(attrs) || opts.lineNumbers === true;

            const wrap = document.createElement('div');
            wrap.className = 'md-code-block';
            const bar = document.createElement('div');
            bar.className = 'md-code-bar';
            const label = document.createElement('span');
            label.className = 'md-code-lang';
            /* 没写语言就不显示标签（不再硬塞一个 text） */
            label.textContent = lang;
            const copy = document.createElement('button');
            copy.type = 'button';
            copy.className = 'md-copy-btn';
            copy.textContent = '复制';
            copy.title = '复制代码';
            copy.addEventListener('click', function () {
                const done = function () {
                    copy.textContent = '已复制';
                    setTimeout(function () { copy.textContent = '复制'; }, 1600);
                };
                if (navigator.clipboard && navigator.clipboard.writeText) {
                    navigator.clipboard.writeText(raw).then(done, function () {});
                } else {
                    const area = document.createElement('textarea');
                    area.value = raw;
                    document.body.appendChild(area);
                    area.select();
                    try { document.execCommand('copy'); done(); } catch (err) { /* ignore */ }
                    document.body.removeChild(area);
                }
            });
            bar.appendChild(label);
            bar.appendChild(copy);

            pre.parentNode.insertBefore(wrap, pre);
            wrap.appendChild(bar);

            if (withNumbers) {
                const lines = raw.split(/\r\n?|\n/).length;
                const gutter = document.createElement('pre');
                gutter.className = 'md-code-gutter';
                const nums = [];
                for (let i = 1; i <= lines; i += 1) nums.push(String(i));
                gutter.textContent = nums.join('\n');
                const body = document.createElement('div');
                body.className = 'md-code-body';
                wrap.appendChild(body);
                body.appendChild(gutter);
                body.appendChild(pre);
            } else {
                wrap.appendChild(pre);
            }
            pre.classList.add('md-code');
        });
    }

    /* B 站视频：用图片语法写链接时渲染成播放器 */
    function decorateVideos(container) {
        const images = Array.prototype.slice.call(container.querySelectorAll('img'));
        images.forEach(function (img) {
            const src = img.getAttribute('src') || '';
            const m = /bilibili\.com\/video\/([A-Za-z0-9]+)/.exec(src);
            if (!m) return;
            const iframe = document.createElement('iframe');
            iframe.className = 'md-bili';
            iframe.src = 'https://player.bilibili.com/player.html?bvid=' + m[1] +
                '&page=1&high_quality=1&autoplay=0';
            iframe.setAttribute('scrolling', 'no');
            iframe.setAttribute('frameborder', '0');
            iframe.setAttribute('allowfullscreen', 'true');
            const box = document.createElement('div');
            box.className = 'md-bili-box';
            box.appendChild(iframe);
            if (img.parentNode) img.parentNode.replaceChild(box, img);
        });
    }

    /* 标题加锚点 id */
    function anchorHeadings(container) {
        const headings = Array.prototype.slice.call(container.querySelectorAll('h1, h2, h3, h4, h5, h6'));
        const used = {};
        headings.forEach(function (h) {
            if (h.id) return;
            let slug = (h.textContent || '').trim().toLowerCase()
                .replace(/[^\w一-龥]+/g, '-').replace(/^-+|-+$/g, '') || 'section';
            if (used[slug]) {
                used[slug] += 1;
                slug = slug + '-' + used[slug];
            } else {
                used[slug] = 1;
            }
            h.id = slug;
        });
    }

    /* 表格后处理：单元格合并 + cute-table */
    function decorateTables(container) {
        const tables = Array.prototype.slice.call(container.querySelectorAll('table'));
        tables.forEach(function (table) {
            mergeTableCells(table);
        });
    }

    /* 找到正文里的 ::cute-table{tuack} 指令，给它后面的第一张表加 class */
    function applyCuteTable(container) {
        const marks = Array.prototype.slice.call(container.querySelectorAll('p'));
        for (let i = 0; i < marks.length; i += 1) {
            const node = marks[i];
            const text = (node.textContent || '').trim();
            if (!/^::cute-table\{tuack\}$/.test(text)) continue;
            // 先记住后面的表格，再删掉这一行
            let table = node.nextElementSibling;
            while (table && table.tagName !== 'TABLE') table = table.nextElementSibling;
            if (node.parentNode) node.parentNode.removeChild(node);
            if (table) table.classList.add('md-cute-table');
        }
    }

    /* 对外接口 */
    function render(container, source, options) {
        if (!container) return;
        container.innerHTML = toHtml(source);
        applyCuteTable(container);
        decorateTables(container);
        decorateCodeBlocks(container, options);
        decorateVideos(container);
        anchorHeadings(container);
    }

    window.CPMarkdown = {
        render: render,
        toHtml: toHtml
    };
})();
