/* ==========================================================================
   CP-IDE — 前端逻辑
   ========================================================================== */
(function () {
    'use strict';

    /* ------------------------------------------------------------------ */
    /*  全局状态                                                            */
    /* ------------------------------------------------------------------ */
    const state = {
        sessionId: '',
        dirty: false,
        samples: [],
        activeSample: -1,
        files: new Map(),          // name -> { name, b64, size }
        lastJudge: null,
        snippets: [],
        editingSnippetId: null,
        positions: {},
        /* ---------------- 多文件标签页 ---------------- */
        tabs: [],                  // { id, name, content, dirty, cursor, scroll, lang, view, asset }
        activeTabId: null,
        split: false,              // 是否左右分栏
        compareTabId: null,        // 右栏正在对比的标签页
        syncScroll: true,          // 左右栏联动滚动
        sideHidden: false,         // 右侧样例侧栏是否被隐藏
        testlib: null,             // 内置 testlib 信息
        checkerScan: null,         // 上传数据扫描结果
        languages: {},             // id -> 语言信息（来自 /api/languages）
        pythonPath: '',            // 自定义 Python 解释器路径
        pythonInterpreter: '',     // 当前使用的解释器（只读展示）
        mdOptions: {               // Markdown 代码块渲染选项
            highlight: true,
            lineNumbers: false
        },
        shortcuts: {},             // 自定义快捷键：{ 功能ID: 'Ctrl+Shift+K' }
        recording: null,           // 正在录制按键的功能 ID
        themePref: 'auto',         // 主题偏好（dark / light / auto）
        lastCompile: null          // 上一次编译的结果（会被保存下来）
    };

    const $ = (id) => document.getElementById(id);
    const ui = {};

    /* 正在读取 / 下载测试数据的任务：评测前会先等它完成 */
    let fileLoadTask = Promise.resolve();

    /* ------------------------------------------------------------------ */
    /*  工具函数                                                            */
    /* ------------------------------------------------------------------ */
    function escapeHtml(text) {
        return String(text == null ? '' : text)
            .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    function toast(message, kind) {
        const stack = $('toastStack');
        const el = document.createElement('div');
        el.className = 'toast' + (kind ? ' ' + kind : '');
        el.textContent = message;
        stack.appendChild(el);
        setTimeout(() => {
            el.style.opacity = '0';
            el.style.transition = 'opacity .25s';
            setTimeout(() => el.remove(), 260);
        }, 3200);
    }

    async function api(path, options) {
        const response = await fetch(path, options);
        let payload;
        try {
            payload = await response.json();
        } catch (err) {
            throw new Error('服务器返回了无法解析的内容（HTTP ' + response.status + '）');
        }
        if (!response.ok && !payload.error) {
            throw new Error('HTTP ' + response.status);
        }
        return payload;
    }

    function postJson(path, body) {
        return api(path, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body)
        });
    }

    function formatBytes(size) {
        if (size < 1024) return size + ' B';
        if (size < 1024 * 1024) return (size / 1024).toFixed(1) + ' KB';
        return (size / 1024 / 1024).toFixed(2) + ' MB';
    }

    function formatTime(ms) {
        if (ms == null) return '-';
        if (ms < 1000) return ms + ' ms';
        return (ms / 1000).toFixed(2) + ' s';
    }

    function formatMemory(kb) {
        if (!kb) return '0 KB';
        if (kb < 1024) return kb + ' KB';
        return (kb / 1024).toFixed(1) + ' MB';
    }

    /* ------------------------------------------------------------------ */
    /*  主题                                                                */
    /* ------------------------------------------------------------------ */
    const THEME_KEY = 'cpide.theme';

    /* 「跟随系统」需要解析成实际主题 */
    function resolveTheme(pref) {
        if (pref !== 'auto') return pref;
        return (window.matchMedia && window.matchMedia('(prefers-color-scheme: light)').matches)
            ? 'light' : 'dark';
    }

    function applyTheme(pref) {
        const theme = resolveTheme(pref);
        document.documentElement.setAttribute('data-theme', theme);
        $('themeIcon').textContent = theme === 'dark' ? '☀' : '☾';
        state.themePref = pref;
        try { localStorage.setItem(THEME_KEY, pref); } catch (err) { /* ignore */ }
        markActive('#themePicker .option-chip', 'theme', pref);
        scheduleSaveWorkspace();
    }

    function toggleTheme() {
        const current = document.documentElement.getAttribute('data-theme');
        applyTheme(current === 'dark' ? 'light' : 'dark');
    }

    /* ------------------------------------------------------------------ */
    /*  外观：代码字体 / 字号                                                */
    /* ------------------------------------------------------------------ */
    const MONO_KEY = 'cpide.monoFont';
    const FONT_SIZE_KEY = 'cpide.editorFontSize';

    /* 字体栈统一写在 CSS 里（html[data-mono="..."]），JS 只负责切换属性，
       这样浏览器缩放 / 系统字体缺失时由 CSS 自然回退。 */
    function applyMonoFont(key, persist) {
        const value = key || 'default';
        document.documentElement.setAttribute('data-mono', value);
        if (persist !== false) {
            try { localStorage.setItem(MONO_KEY, value); } catch (err) { /* ignore */ }
        }
        markActive('#fontPicker .option-card', 'mono', value);
        // CodeMirror 需要重新测量字符宽度，否则换字体后光标会错位
        refreshEditors();
        scheduleSaveWorkspace();
    }

    function applyEditorFontSize(size, persist) {
        const value = size || '13.5';
        document.documentElement.style.setProperty('--editor-font-size', value + 'px');
        if (persist !== false) {
            try { localStorage.setItem(FONT_SIZE_KEY, value); } catch (err) { /* ignore */ }
        }
        markActive('#fontSizePicker .option-chip', 'size', value);
        refreshEditors();
        scheduleSaveWorkspace();
    }

    /* 两个（以及更多）编辑器一起重新测量 */
    function refreshEditors() {
        setTimeout(() => {
            state.tabs.forEach((tab) => {
                if (tab.cm) tab.cm.refresh();
            });
        }, 30);
    }

    /* 标记按钮组中当前选中项 */
    function markActive(selector, attr, value) {
        document.querySelectorAll(selector).forEach((el) => {
            const on = el.dataset[attr] === value;
            el.classList.toggle('active', on);
            el.setAttribute('aria-pressed', on ? 'true' : 'false');
        });
    }

    /* ------------------------------------------------------------------ */
    /*  编辑器                                                              */
    /* ------------------------------------------------------------------ */
    let cm = null;            // 左栏（当前编辑目标）
    let cm2 = null;           // 右栏（分栏对比）
    let suppressChange = false;
    let tabSeq = 0;
    let syncingScroll = false;

    const DEFAULT_CODE = `#include <bits/stdc++.h>
using namespace std;

int main() {
    ios::sync_with_stdio(false);
    cin.tie(nullptr);

    int n;
    cin >> n;
    long long sum = 0;
    for (int i = 0; i < n; ++i) {
        long long x;
        cin >> x;
        sum += x;
    }
    cout << sum << '\\n';
    return 0;
}
`;

    const CM_OPTIONS = {
        lineNumbers: true,
        mode: 'text/x-c++src',
        indentUnit: 4,
        tabSize: 4,
        indentWithTabs: false,
        lineWrapping: false,
        styleActiveLine: true,
        matchBrackets: true,
        autoCloseBrackets: true,
        /* 快捷键统一在 buildEditorExtraKeys() 里生成，
           每个编辑器实例创建后再单独注入，方便随时改键。 */
        extraKeys: {},
        viewportMargin: 30
    };

    /* 每个标签页拥有独立的 CodeMirror 实例：
       这样切换标签时不会丢撤销历史，也不会把别的文件的内容撤销回来。
       实例在标签页第一次显示时才创建，开很多标签也不会拖慢启动。 */
    function createEditorFor(tab) {
        if (tab.cm) return tab.cm;
        const textarea = document.createElement('textarea');
        $('cmPark').appendChild(textarea);
        const instance = CodeMirror.fromTextArea(textarea, CM_OPTIONS);
        instance.setValue(tab.content || '');
        instance.on('change', () => {
            if (suppressChange) return;
            tab.content = instance.getValue();
            markTabDirty(tab);
            if (tab.id === state.activeTabId) {
                state.dirty = true;
                $('dirtyBadge').hidden = false;
                updateStats();
                if (tab.lang && tab.lang.kind === 'markdown') refreshDocView('left');
            }
            if (tab.id === state.compareTabId) updateStats2();
            scheduleSaveTabs();
        });
        instance.on('cursorActivity', () => {
            if (tab.id === state.activeTabId) updateCursor();
            if (tab.id === state.compareTabId) updateCursor2();
        });
        instance.on('scroll', () => {
            if (!state.split || !state.syncScroll) return;
            let other = null;
            if (tab.id === state.activeTabId) other = cm2;
            else if (tab.id === state.compareTabId) other = cm;
            if (other) syncScroll(instance, other);
        });
        tab.cm = instance;
        /* 新建的编辑器也要拿到最新的快捷键表 */
        try { instance.setOption('extraKeys', buildEditorExtraKeys()); } catch (err) { /* ignore */ }
        return instance;
    }

    /* 把某个标签页的编辑器挂到左栏 / 右栏 */
    function attachEditor(tab, slot) {
        if (!tab || !tab.cm) return;
        const host = slot === 'right' ? $('hostRight') : $('hostLeft');
        const wrapper = tab.cm.getWrapperElement();
        if (wrapper.parentElement !== host) {
            host.appendChild(wrapper);
            setTimeout(() => tab.cm.refresh(), 0);
        }
    }

    /* 不在显示中的编辑器收到停车位，避免同时渲染多个大文件 */
    function parkOtherEditors() {
        const park = $('cmPark');
        state.tabs.forEach((tab) => {
            if (!tab.cm) return;
            if (tab.id === state.activeTabId) return;
            if (state.split && tab.id === state.compareTabId) return;
            const wrapper = tab.cm.getWrapperElement();
            if (wrapper.parentElement !== park) park.appendChild(wrapper);
        });
    }

    function showActiveEditor() {
        const tab = getActiveTab();
        if (!tab) {
            cm = null;
            updateEmptyState();
            return;
        }
        cm = createEditorFor(tab);
        attachEditor(tab, 'left');
        parkOtherEditors();
        applyTabLanguage(tab);
        updateStats();
        updateCursor();
        updateHeaderFileName();
        updateEmptyState();
    }

    /* 一个文件都没打开时，编辑器区域给个提示，而不是留一块空白 */
    function updateEmptyState() {
        const box = $('editorEmpty');
        if (!box) return;
        const empty = state.tabs.length === 0;
        box.hidden = !empty;
        const wrap = $('wrapLeft');
        if (wrap) wrap.classList.toggle('is-empty', empty);
        const info = $('tabInfo');
        if (info) info.textContent = empty ? '没有文件' : (state.tabs.length + ' 个文件');
    }

    function showCompareEditor() {
        const tab = getTab(state.compareTabId);
        if (!tab) {
            cm2 = null;
            refreshDocView('right');
            return;
        }
        cm2 = createEditorFor(tab);
        attachEditor(tab, 'right');
        if (cm2) cm2.setOption('mode', (tab.lang || LANG_FALLBACK.text).cm_mode);
        const badge2 = $('langBadge2');
        if (badge2) {
            badge2.textContent = (tab.lang || LANG_FALLBACK.text).name;
            badge2.className = 'lang-badge ' + (tab.lang || LANG_FALLBACK.text).id;
        }
        refreshDocView('right');
        updateStats2();
        updateCursor2();
    }

    function updateStats() {
        if (!cm) return;
        const lines = cm.lineCount();
        const text = cm.getValue();
        const chars = text.length;
        $('codeStats').textContent = lines + ' 行 · ' + chars + ' 字符';
    }

    function updateStats2() {
        const el = $('codeStats2');
        if (!el || !cm2) return;
        el.textContent = cm2.lineCount() + ' 行 · ' + cm2.getValue().length + ' 字符';
    }

    function updateCursor() {
        if (!cm) return;
        const pos = cm.getCursor();
        $('cursorInfo').textContent = '行 ' + (pos.line + 1) + '，列 ' + (pos.ch + 1);
    }

    function updateCursor2() {
        const el = $('cursorInfo2');
        if (!el || !cm2) return;
        const pos = cm2.getCursor();
        el.textContent = '行 ' + (pos.line + 1) + '，列 ' + (pos.ch + 1);
    }

    /* ------------------------------------------------------------------ */
    /*  快捷键                                                              */
    /* ------------------------------------------------------------------ */
    /* 所有能改的快捷键都登记在这里：
         scope = 'global' —— 由页面最外层的 keydown 统一分发（任何地方都能按）
         scope = 'editor' —— 注入 CodeMirror 的 extraKeys，只在编辑器里生效
       keys 用统一写法：'Ctrl' / 'Alt' / 'Shift' + '+' + 按键名，例如 'Ctrl+Shift+F'
       用户改过的键位存在 state.shortcuts 里（只存改过的，升级后仍能用默认值）。 */
    const SHORTCUT_DEFS = [
        /* ---------------- 全局 ---------------- */
        { id: 'compile', group: '编译与运行', scope: 'global', keys: 'Ctrl+B',
          label: '编译', run: () => compileCode() },
        { id: 'compileRun', group: '编译与运行', scope: 'global', keys: 'Ctrl+Enter',
          label: '编译并运行', run: () => compileAndRun() },
        { id: 'runSample', group: '编译与运行', scope: 'global', keys: 'F5',
          label: '运行当前样例', run: () => { switchMode('sample'); runSample(); } },
        { id: 'judgeAll', group: '编译与运行', scope: 'global', keys: 'Ctrl+J',
          label: '批量评测', run: () => { switchMode('judge'); judgeAll(); } },
        { id: 'formatView', group: '编译与运行', scope: 'global', keys: 'Ctrl+Shift+F',
          label: '格式化对比视图', run: () => openFormatView() },
        { id: 'exportFile', group: '文件', scope: 'global', keys: 'Ctrl+S',
          label: '导出当前文件', run: () => exportCurrentFile() },
        { id: 'newTab', group: '文件', scope: 'global', keys: 'Alt+N',
          label: '新建标签页', run: () => newTab() },
        { id: 'closeTab', group: '文件', scope: 'global', keys: 'Alt+W',
          label: '关闭当前标签页', run: () => requestCloseTab(state.activeTabId) },
        { id: 'toggleTheme', group: '外观与视图', scope: 'global', keys: 'Ctrl+D',
          label: '切换深色 / 浅色', run: () => toggleTheme() },
        { id: 'toggleSplit', group: '外观与视图', scope: 'global', keys: 'Alt+S',
          label: '开关左右分栏', run: () => toggleSplit() },
        { id: 'toggleSide', group: '外观与视图', scope: 'global', keys: 'Alt+H',
          label: '隐藏 / 显示右侧侧栏', run: () => toggleSide() },
        { id: 'prevTab', group: '外观与视图', scope: 'global', keys: 'Alt+ArrowLeft',
          label: '上一个标签页', run: () => switchTabOffset(-1) },
        { id: 'nextTab', group: '外观与视图', scope: 'global', keys: 'Alt+ArrowRight',
          label: '下一个标签页', run: () => switchTabOffset(1) },
        { id: 'closePanel', group: '外观与视图', scope: 'global', keys: 'Escape',
          label: '关闭弹窗 / 设置抽屉', run: () => closeTopPanel() },

        /* ---------------- 编辑器内 ---------------- */
        { id: 'edCompile', group: '代码编辑器', scope: 'editor', keys: 'Ctrl+Alt+Enter',
          cm: 'Ctrl-Alt-Enter', label: '编译', cmd: () => compileCode() },
        { id: 'edAutocomplete', group: '代码编辑器', scope: 'editor', keys: 'Ctrl+Space',
          cm: 'Ctrl-Space', label: '自动补全', cmd: 'autocomplete' },
        { id: 'edComment', group: '代码编辑器', scope: 'editor', keys: 'Ctrl+/',
          cm: 'Ctrl-/', label: '注释 / 取消注释', cmd: 'toggleComment' },
        { id: 'edIndent', group: '代码编辑器', scope: 'editor', keys: 'Shift+Tab',
          cm: 'Shift-Tab', label: '反缩进', cmd: 'indentLess' },
        { id: 'edFind', group: '查找', scope: 'editor', keys: 'Ctrl+F',
          cm: 'Ctrl-F', label: '查找', cmd: 'find' },
        { id: 'edReplace', group: '查找', scope: 'editor', keys: 'Ctrl+H',
          cm: 'Ctrl-H', label: '查找替换', cmd: 'replace' },
        { id: 'edFindNext', group: '查找', scope: 'editor', keys: 'Ctrl+G',
          cm: 'Ctrl-G', label: '查找下一个', cmd: 'findNext' },
        { id: 'edFindPrev', group: '查找', scope: 'editor', keys: 'Ctrl+Shift+G',
          cm: 'Shift-Ctrl-G', label: '查找上一个', cmd: 'findPrev' },
        { id: 'edUndo', group: '代码编辑器', scope: 'editor', keys: 'Ctrl+Z',
          cm: 'Ctrl-Z', label: '撤销', cmd: 'undo' },
        { id: 'edRedo', group: '代码编辑器', scope: 'editor', keys: 'Ctrl+Y',
          cm: 'Ctrl-Y', label: '重做', cmd: 'redo' }
    ];

    /* CodeMirror 自带、但会被我们接管的键位：统一置空，避免和新绑定的键同时触发 */
    const CM_TAKEOVER_KEYS = ['Shift-Ctrl-F', 'Ctrl-S', 'Ctrl-D', 'Alt-Left', 'Alt-Right'];

    /* 按键名归一化：把浏览器事件转成 'Ctrl+Shift+F' 这样的字符串 */
    function canonFromEvent(event) {
        const mods = [];
        if (event.ctrlKey || event.metaKey) mods.push('Ctrl');
        if (event.altKey) mods.push('Alt');
        if (event.shiftKey) mods.push('Shift');
        let key = event.key;
        if (!key || key === 'Unidentified') return '';
        if (key === ' ' || key === 'Spacebar') key = 'Space';
        else if (key.length === 1) key = key.toUpperCase();
        else if (/^Arrow/.test(key)) { /* ArrowLeft 等保持原样 */ }
        else if (/^F\d{1,2}$/.test(key)) { /* 功能键保持原样 */ }
        else key = key.charAt(0).toUpperCase() + key.slice(1);
        if (mods.indexOf('Shift') >= 0 && key.length === 1) key = key.toUpperCase();
        return mods.concat([key]).join('+');
    }

    /* 归一化串 -> CodeMirror 的写法（'Ctrl+Shift+F' -> 'Shift-Ctrl-F'） */
    function toCmName(chord) {
        if (!chord) return '';
        const parts = chord.split('+');
        const key = parts.pop();
        const mods = [];
        if (parts.indexOf('Shift') >= 0) mods.push('Shift');
        if (parts.indexOf('Ctrl') >= 0) mods.push('Ctrl');
        if (parts.indexOf('Alt') >= 0) mods.push('Alt');
        const cmKey = {
            Escape: 'Esc', ArrowLeft: 'Left', ArrowRight: 'Right',
            ArrowUp: 'Up', ArrowDown: 'Down', Space: 'Space'
        }[key] || key;
        return mods.concat([cmKey]).join('-');
    }

    /* 显示用：'Ctrl+Shift+F' -> 'Ctrl + Shift + F' */
    function prettyChord(chord) {
        if (!chord) return '未绑定';
        return chord.split('+').map((part) => {
            if (part === 'ArrowLeft') return '←';
            if (part === 'ArrowRight') return '→';
            if (part === 'ArrowUp') return '↑';
            if (part === 'ArrowDown') return '↓';
            return part;
        }).join(' + ');
    }

    function shortcutDef(id) {
        return SHORTCUT_DEFS.find((d) => d.id === id) || null;
    }

    /* 当前生效的键位：用户改过就用改过的 */
    function currentChord(def) {
        const saved = state.shortcuts[def.id];
        return (saved === undefined || saved === null) ? def.keys : saved;
    }

    /* 记录所有全局快捷键，供 keydown 分发时查表 */
    let globalChordMap = new Map();

    function rebuildGlobalChordMap() {
        globalChordMap = new Map();
        SHORTCUT_DEFS.forEach((def) => {
            if (def.scope !== 'global') return;
            const chord = currentChord(def);
            if (!chord) return;
            if (!globalChordMap.has(chord)) globalChordMap.set(chord, def);
        });
    }

    /* 编辑器快捷键表：把每条映射交给 CodeMirror 的 extraKeys */
    function buildEditorExtraKeys() {
        const map = {};
        const used = new Set();
        SHORTCUT_DEFS.forEach((def) => {
            if (def.scope !== 'editor') return;
            const name = toCmName(currentChord(def));
            if (name) used.add(name);
        });
        /* 先把 CodeMirror 自带、我们要接管的键位清空 */
        CM_TAKEOVER_KEYS.forEach((name) => {
            if (!used.has(name)) map[name] = () => { /* 已被 IDE 接管 */ };
        });
        SHORTCUT_DEFS.forEach((def) => {
            if (def.scope !== 'editor') return;
            const name = toCmName(currentChord(def));
            if (name) map[name] = def.cmd;
            /* 默认键位被改走后，把原来的键位也清掉，免得两个功能一起触发 */
            if (def.cm && name !== def.cm && !used.has(def.cm)) map[def.cm] = () => { /* 已改绑 */ };
        });
        return map;
    }

    /* 把最新的编辑器键位表同步给所有已经创建的编辑器 */
    function applyEditorShortcuts() {
        const map = buildEditorExtraKeys();
        state.tabs.forEach((tab) => {
            if (tab.cm) tab.cm.setOption('extraKeys', map);
        });
    }

    /* Escape：关掉最上面那层浮层 */
    function closeTopPanel() {
        if (!$('confirmBar').hidden) { closeConfirm(false); return true; }
        if (!$('formatModal').hidden) { closeFormatView(); return true; }
        if (!$('toolsDrawer').hidden) { closeTools(); return true; }
        return false;
    }

    /* ------------------------------------------------------------------ */
    /*  快捷键设置面板                                                     */
    /* ------------------------------------------------------------------ */
    function renderShortcutPanel() {
        const box = $('keysList');
        if (!box) return;
        const filter = (($('keysFilter') && $('keysFilter').value) || '').trim().toLowerCase();
        const groups = [];
        SHORTCUT_DEFS.forEach((def) => {
            if (filter && def.label.toLowerCase().indexOf(filter) < 0
                && def.group.toLowerCase().indexOf(filter) < 0) return;
            let group = groups.find((g) => g.name === def.group);
            if (!group) { group = { name: def.group, items: [] }; groups.push(group); }
            group.items.push(def);
        });
        if (!groups.length) {
            box.innerHTML = '<p class="field-hint">没有匹配的快捷键。</p>';
            return;
        }
        box.innerHTML = groups.map((group) => (
            '<div class="keys-group">'
            + '<div class="keys-group-title">' + escapeHtml(group.name) + '</div>'
            + group.items.map((def) => {
                const chord = currentChord(def);
                const custom = state.shortcuts[def.id] !== undefined;
                const recording = state.recording === def.id;
                return '<div class="keys-row' + (recording ? ' recording' : '') + '" data-id="' + def.id + '">'
                    + '<span class="keys-label">' + escapeHtml(def.label) + '</span>'
                    + '<span class="keys-scope">' + (def.scope === 'editor' ? '编辑器' : '全局') + '</span>'
                    + '<button type="button" class="keys-chord' + (custom ? ' custom' : '') + '" data-id="' + def.id + '">'
                    + (recording ? '按下按键…' : escapeHtml(prettyChord(chord))) + '</button>'
                    + (custom ? '<button type="button" class="keys-reset" data-id="' + def.id + '" title="恢复默认（'
                        + escapeHtml(prettyChord(def.keys)) + '）">恢复</button>' : '')
                    + '</div>';
            }).join('')
            + '</div>'
        )).join('');

        box.querySelectorAll('.keys-chord').forEach((btn) => {
            btn.addEventListener('click', () => startRecording(btn.dataset.id));
        });
        box.querySelectorAll('.keys-reset').forEach((btn) => {
            btn.addEventListener('click', () => resetShortcut(btn.dataset.id));
        });
    }

    /* 开始录制：下一次按键就作为新快捷键 */
    function startRecording(id) {
        if (!shortcutDef(id)) return;
        state.recording = id;
        renderShortcutPanel();
        toast('按下新的按键组合（Esc 取消，Backspace 删除该快捷键）', '');
    }

    function stopRecording() {
        state.recording = null;
        renderShortcutPanel();
    }

    /* 冲突检查：同一个键位不能被两个功能同时占用 */
    function findChordConflict(id, chord) {
        return SHORTCUT_DEFS.find((def) => {
            if (def.id === id) return false;
            return currentChord(def) === chord;
        }) || null;
    }

    function setShortcut(id, chord) {
        const def = shortcutDef(id);
        if (!def) return;
        const conflict = findChordConflict(id, chord);
        if (conflict) {
            toast('该键位已被「' + conflict.label + '」占用，请换一个', 'err');
            return;
        }
        if (chord === def.keys || !chord) delete state.shortcuts[id];
        else state.shortcuts[id] = chord;
        persistShortcuts();
        rebuildGlobalChordMap();
        applyEditorShortcuts();
        renderShortcutPanel();
        toast('「' + def.label + '」已设为 ' + prettyChord(currentChord(def)), '');
    }

    function resetShortcut(id) {
        const def = shortcutDef(id);
        if (!def) return;
        delete state.shortcuts[id];
        persistShortcuts();
        rebuildGlobalChordMap();
        applyEditorShortcuts();
        renderShortcutPanel();
        toast('「' + def.label + '」已恢复默认', '');
    }

    function resetAllShortcuts() {
        state.shortcuts = {};
        persistShortcuts();
        rebuildGlobalChordMap();
        applyEditorShortcuts();
        renderShortcutPanel();
        toast('所有快捷键已恢复默认', '');
    }

    /* 快捷键也要跟着工作区一起保存（换电脑 / 换浏览器都还在） */
    function persistShortcuts() {
        try {
            localStorage.setItem('cpide.shortcuts', JSON.stringify(state.shortcuts));
        } catch (err) { /* ignore */ }
        scheduleSaveWorkspace();
    }

    function loadShortcuts(saved) {
        let data = saved;
        if (data === undefined || data === null) {
            try { data = JSON.parse(localStorage.getItem('cpide.shortcuts') || '{}'); }
            catch (err) { data = {}; }
        }
        state.shortcuts = (data && typeof data === 'object') ? data : {};
        rebuildGlobalChordMap();
    }

    /* ------------------------------------------------------------------ */
    /*  多文件标签页                                                        */
    /* ------------------------------------------------------------------ */
    const TABS_KEY = 'cpide.tabs';
    let saveTabsTimer = null;

    function nextTabId() {
        tabSeq += 1;
        return 'tab-' + tabSeq;
    }

    function getTab(id) {
        if (!id) return null;
        for (let i = 0; i < state.tabs.length; i += 1) {
            if (state.tabs[i].id === id) return state.tabs[i];
        }
        return null;
    }

    function getActiveTab() {
        return getTab(state.activeTabId);
    }

    function createTab(name, content, options) {
        const opts = options || {};
        const tab = {
            id: nextTabId(),
            name: name || 'untitled.cpp',
            content: typeof content === 'string' ? content : '',
            dirty: !!opts.dirty,
            cursor: { line: 0, ch: 0 },
            scroll: 0,
            lang: detectLanguage(name || ''),
            view: 'edit',
            asset: opts.asset || null
        };
        state.tabs.push(tab);
        return tab;
    }

    /* ------------------------------------------------------------------ */
    /*  语言                                                                */
    /* ------------------------------------------------------------------ */
    const LANG_FALLBACK = {
        cpp: { id: 'cpp', name: 'C++', cm_mode: 'text/x-c++src', kind: 'code', runnable: true, editable: true },
        python: { id: 'python', name: 'Python', cm_mode: 'text/x-python', kind: 'code', runnable: true, editable: true },
        markdown: { id: 'markdown', name: 'Markdown', cm_mode: 'text/x-markdown', kind: 'markdown', runnable: false, editable: true },
        pdf: { id: 'pdf', name: 'PDF', cm_mode: 'text/plain', kind: 'pdf', runnable: false, editable: false },
        text: { id: 'text', name: '纯文本', cm_mode: 'text/plain', kind: 'text', runnable: false, editable: true }
    };

    const LANG_BY_EXT = {
        cpp: ['.cpp', '.cxx', '.cc', '.c', '.h', '.hpp', '.hh', '.hxx', '.inl'],
        python: ['.py', '.pyw', '.pyi'],
        markdown: ['.md', '.markdown', '.mdown', '.mkd'],
        pdf: ['.pdf'],
        text: ['.txt', '.log', '.json', '.yaml', '.yml', '.toml', '.ini', '.cfg',
            '.conf', '.csv', '.tsv', '.in', '.out', '.sql', '.sh', '.bat', '.xml', '.html', '.css']
    };

    /* 根据文件名判断语言 */
    function detectLanguage(name) {
        const dot = (name || '').lastIndexOf('.');
        const ext = dot >= 0 ? (name || '').slice(dot).toLowerCase() : '';
        for (const id of Object.keys(LANG_BY_EXT)) {
            if (LANG_BY_EXT[id].indexOf(ext) >= 0) {
                return state.languages[id] || LANG_FALLBACK[id];
            }
        }
        return state.languages.text || LANG_FALLBACK.text;
    }

    function activeLanguage() {
        const tab = getActiveTab();
        return (tab && tab.lang) || LANG_FALLBACK.cpp;
    }

    /* 切换标签页后：更新编辑器语法、徽标、文档视图 */
    function applyTabLanguage(tab) {
        if (!tab) return;
        const lang = tab.lang || LANG_FALLBACK.text;
        if (cm) cm.setOption('mode', lang.cm_mode);
        const badge = $('langBadge');
        if (badge) {
            badge.textContent = lang.name;
            badge.className = 'lang-badge ' + lang.id;
        }
        const badge2 = $('langBadge2');
        if (badge2) {
            badge2.textContent = '';
            badge2.className = 'lang-badge';
        }
        updateViewToggle();
        refreshDocView('left');
        applyLanguageSettings();
        updateCheckerHint();
    }

    function updateViewToggle() {
        const btn = $('btnToggleView');
        if (!btn) return;
        const tab = getActiveTab();
        const lang = (tab && tab.lang) || LANG_FALLBACK.text;
        const show = lang.kind === 'markdown';
        btn.hidden = !show;
        btn.textContent = (tab && tab.view === 'preview') ? '✎' : '👁';
        btn.title = (tab && tab.view === 'preview') ? '回到源码编辑' : '预览渲染效果';
    }

    /* 文档视图：Markdown 预览 / PDF 阅读 */
    function refreshDocView(slot) {        const tab = slot === 'right' ? getTab(state.compareTabId) : getActiveTab();
        const box = slot === 'right' ? $('docRight') : $('docLeft');
        const wrap = slot === 'right' ? $('wrapRight') : $('wrapLeft');
        if (!box || !wrap) return;
        const lang = (tab && tab.lang) || LANG_FALLBACK.text;

        if (!tab || lang.kind === 'code' || (lang.kind === 'markdown' && tab.view !== 'preview')) {
            box.hidden = true;
            box.innerHTML = '';
            wrap.hidden = false;
            return;
        }
        wrap.hidden = true;
        box.hidden = false;
        if (lang.kind === 'markdown') {
            renderMarkdown(box, tab.content || '');
        } else if (lang.kind === 'pdf') {
            renderPdf(box, tab);
        }
    }

    /* 两个文档预览一起刷新（改了代码块的高亮 / 行号选项后要用） */
    function refreshDocPreviews() {
        refreshDocView('left');
        refreshDocView('right');
    }

    /* ------------------------------ Markdown ------------------------------ */
    /* 具体渲染交给 md-enhance.js：洛谷扩展语法（折叠框 / 表格合并 / 对齐 /
       引言 / Tuack 表格 / 复制按钮 / 自动链接 / Bilibili 视频等）都在那里实现。 */
    function renderMarkdown(container, text) {
        container.className = 'doc-view md-body';
        if (window.CPMarkdown && window.CPMarkdown.render) {
            window.CPMarkdown.render(container, text, {
                highlight: state.mdOptions.highlight !== false,
                lineNumbers: !!state.mdOptions.lineNumbers
            });
            return;
        }
        /* 兜底：扩展渲染器没加载时，至少把原文显示出来 */
        container.innerHTML = '<pre>' + escapeHtml(text || '') + '</pre>';
    }

    /* ------------------------------ PDF ------------------------------ */
    let pdfRenderToken = 0;

    function renderPdf(container, tab) {
        const asset = tab && tab.asset;
        container.className = 'doc-view pdf-view';
        container.innerHTML = '<div class="pdf-toolbar"><span class="pdf-name">' +
            escapeHtml(tab.name) + '</span><span class="spacer"></span>' +
            '<button class="mini-btn" data-pdf="prev">‹ 上一页</button>' +
            '<span class="pdf-page">1 / ?</span>' +
            '<button class="mini-btn" data-pdf="next">下一页 ›</button>' +
            '<button class="mini-btn" data-pdf="zoom-out">－</button>' +
            '<button class="mini-btn" data-pdf="zoom-in">＋</button>' +
            '<button class="mini-btn" data-pdf="actual" title="按原始大小显示（PDF 的 96 DPI）">100%</button>' +
            '<button class="mini-btn" data-pdf="fit-width" title="宽度适应窗口">宽度</button>' +
            '<button class="mini-btn" data-pdf="open">用系统程序打开</button></div>' +
            '<div class="pdf-canvas-wrap"><p class="pdf-error">正在加载…</p></div>';

        if (!asset || !asset.token) {
            container.querySelector('.pdf-canvas-wrap').innerHTML =
                '<p class="pdf-error">这个 PDF 已经失效了，请重新打开文件。</p>';
            return;
        }

        const myToken = ++pdfRenderToken;
        const lib = window.pdfjsLib;
        if (!lib) {
            container.querySelector('.pdf-canvas-wrap').innerHTML =
                '<p class="pdf-error">PDF 组件没有加载成功。</p>';
            return;
        }
        if (lib.GlobalWorkerOptions) {
            lib.GlobalWorkerOptions.workerSrc = '/static/vendor/pdfjs/pdf.worker.min.js';
        }

        const wrap = container.querySelector('.pdf-canvas-wrap');
        const pageLabel = container.querySelector('.pdf-page');
        let doc = null;
        let page = 1;
        let zoomMode = 'actual'; // actual=原始大小 / width=适应宽度 / manual=手动
        let userScale = 0;
        let lastScale = 1;

        /* 缩放策略：
           默认按 PDF 的原始大小（96 DPI，与浏览器 PDF 阅读器一致）显示，
           页面比窗口高时就在下方滚动查看，和 Markdown 预览一样；
           只有宽度实在放不下时，才退让成「适应宽度」，绝不把页面缩得很小。 */
        const NATURAL_SCALE = 96 / 72;
        const targetScale = (pdfPage) => {
            if (zoomMode === 'manual' && userScale > 0) return userScale;
            const base = pdfPage.getViewport({ scale: 1 });
            const availW = Math.max(200, (wrap.clientWidth || 640) - 36);
            const byWidth = availW / base.width;
            if (zoomMode === 'width') {
                return Math.min(3, Math.max(0.3, byWidth));
            }
            return Math.min(NATURAL_SCALE, byWidth);
        };

        const draw = (num) => {
            if (!doc) return;
            doc.getPage(num).then((pdfPage) => {
                if (myToken !== pdfRenderToken) return;
                const useScale = targetScale(pdfPage);
                lastScale = useScale;
                // 按设备像素比渲染，文字才够清晰（逻辑尺寸不变，显示为原始大小）
                const dpr = Math.max(1, Math.min(3, window.devicePixelRatio || 1));
                const logical = pdfPage.getViewport({ scale: useScale });
                const viewport = pdfPage.getViewport({ scale: useScale * dpr });
                const canvas = document.createElement('canvas');
                canvas.width = Math.max(1, Math.floor(viewport.width));
                canvas.height = Math.max(1, Math.floor(viewport.height));
                canvas.style.width = Math.max(1, Math.floor(logical.width)) + 'px';
                canvas.style.height = Math.max(1, Math.floor(logical.height)) + 'px';
                wrap.innerHTML = '';
                wrap.appendChild(canvas);
                const context = canvas.getContext('2d');
                const task = pdfPage.render({ canvasContext: context, viewport: viewport });
                // pdf.js 3.x 的 render() 返回 Task（.promise），4.x 直接返回 Promise
                const done = (task && task.promise) ? task.promise : Promise.resolve(task);
                done.then(() => {
                    if (myToken !== pdfRenderToken) return;
                    pageLabel.textContent = num + ' / ' + doc.numPages;
                }).catch((err) => {
                    wrap.innerHTML = '<p class="pdf-error">渲染失败：' + escapeHtml(err.message) + '</p>';
                });
            }).catch((err) => {
                wrap.innerHTML = '<p class="pdf-error">打开失败：' + escapeHtml(err.message) + '</p>';
            });
        };

        lib.getDocument({ url: '/api/assets/' + asset.token }).promise.then((pdfDoc) => {
            if (myToken !== pdfRenderToken) return;
            doc = pdfDoc;
            page = 1;
            draw(1);
            // 布局稳定后再按真实尺寸重画一次，保证「整页」真的塞得进窗口
            setTimeout(() => {
                if (myToken === pdfRenderToken && zoomMode !== 'manual') draw(page);
            }, 120);
        }).catch((err) => {
            if (myToken !== pdfRenderToken) return;
            wrap.innerHTML = '<p class="pdf-error">打开失败：' + escapeHtml(err.message) + '</p>';
        });

        container.querySelector('.pdf-toolbar').addEventListener('click', (event) => {
            const action = event.target.dataset ? event.target.dataset.pdf : '';
            if (!action || !doc) return;
            if (action === 'prev' && page > 1) { page -= 1; draw(page); }
            else if (action === 'next' && page < doc.numPages) { page += 1; draw(page); }
            else if (action === 'zoom-in') {
                zoomMode = 'manual';
                userScale = Math.min(4, (userScale || lastScale) + 0.25);
                draw(page);
            } else if (action === 'zoom-out') {
                zoomMode = 'manual';
                userScale = Math.max(0.2, (userScale || lastScale) - 0.25);
                draw(page);
            } else if (action === 'actual') { zoomMode = 'actual'; userScale = 0; draw(page); }
            else if (action === 'fit-width') { zoomMode = 'width'; userScale = 0; draw(page); }
            else if (action === 'open') { openAssetExternally(asset.token); }
        });

        /* 窗口大小变化时，按新的尺寸重新适配 */
        let resizeTimer = null;
        const onResize = () => {
            if (resizeTimer) clearTimeout(resizeTimer);
            resizeTimer = setTimeout(() => {
                if (myToken === pdfRenderToken && zoomMode !== 'manual') draw(page);
            }, 180);
        };
        window.addEventListener('resize', onResize);
    }

    function openAssetExternally(token) {
        postJson('/api/assets/open', { token: token })
            .then((result) => {
                if (!result.ok) toast(result.error || '打开失败', 'err');
            })
            .catch((err) => toast('打开失败：' + err.message, 'err'));
    }

    /* 生成不重名的文件名 */
    function uniqueName(base) {
        let name = base;
        let index = 2;
        while (state.tabs.some((tab) => tab.name === name)) {
            const dot = base.lastIndexOf('.');
            name = dot > 0
                ? base.slice(0, dot) + '-' + index + base.slice(dot)
                : base + '-' + index;
            index += 1;
        }
        return name;
    }

    function activateTab(id) {
        const tab = getTab(id);
        if (!tab || id === state.activeTabId) return;
        state.activeTabId = id;
        // 右栏不能和左栏显示同一个文件，冲突时自动换一个
        if (state.split && state.compareTabId === id) {
            const others = state.tabs.filter((item) => item.id !== id);
            state.compareTabId = others.length ? others[0].id : null;
        }
        showActiveEditor();
        if (state.split) showCompareEditor();
        renderTabs();
        renderCompareSelect();
        scheduleSaveTabs();
    }

    function markTabDirty(tab) {
        if (!tab || tab.dirty) return;
        tab.dirty = true;
        const dot = document.querySelector('.code-tab[data-tab-id="' + tab.id + '"] .tab-dirty');
        if (dot) dot.hidden = false;
        else renderTabs();
    }

    function renderTabs() {
        const strip = $('tabStrip');
        strip.innerHTML = '';
        state.tabs.forEach((tab) => {
            const el = document.createElement('div');
            el.className = 'code-tab' + (tab.id === state.activeTabId ? ' active' : '');
            el.dataset.tabId = tab.id;
            el.setAttribute('role', 'tab');
            el.setAttribute('aria-selected', tab.id === state.activeTabId ? 'true' : 'false');
            el.title = tab.name + (tab.dirty ? '（已修改）' : '') +
                (tab.lang ? ' · ' + tab.lang.name : '');

            const name = document.createElement('span');
            name.className = 'tab-name';
            name.textContent = tab.name;

            const dirty = document.createElement('span');
            dirty.className = 'tab-dirty';
            dirty.hidden = !tab.dirty;

            const close = document.createElement('button');
            close.className = 'tab-close';
            close.textContent = '✕';
            close.title = '关闭标签页';
            close.addEventListener('click', (event) => {
                event.stopPropagation();
                requestCloseTab(tab.id);
            });

            el.appendChild(name);
            el.appendChild(dirty);
            el.appendChild(close);
            el.addEventListener('click', () => activateTab(tab.id));
            el.addEventListener('dblclick', (event) => {
                event.preventDefault();
                startRename(tab.id);
            });
            strip.appendChild(el);
        });
        updateEmptyState();
    }

    function updateHeaderFileName() {
        const tab = getActiveTab();
        const input = $('fileName');
        if (!tab) {
            input.value = '';
            $('dirtyBadge').hidden = true;
            return;
        }
        if (document.activeElement !== input) input.value = tab.name;
        $('dirtyBadge').hidden = !tab.dirty;
        state.dirty = !!tab.dirty;
    }

    function renameTab(id, newName) {
        const tab = getTab(id);
        if (!tab) return;
        const name = (newName || '').trim();
        if (!name) {
            renderTabs();
            updateHeaderFileName();
            return;
        }
        if (state.tabs.some((other) => other.id !== id && other.name === name)) {
            toast('已经有一个叫「' + name + '」的文件了', 'warn');
            renderTabs();
            updateHeaderFileName();
            return;
        }
        tab.name = name;
        tab.lang = detectLanguage(name);
        renderTabs();
        renderCompareSelect();
        updateHeaderFileName();
        applyTabLanguage(tab);
        scheduleSaveTabs();
    }

    /* 双击标签页 -> 就地重命名 */
    function startRename(id) {
        const tab = getTab(id);
        if (!tab) return;
        activateTab(id);
        const el = document.querySelector('.code-tab[data-tab-id="' + id + '"]');
        if (!el) return;
        const label = el.querySelector('.tab-name');
        if (!label) return;
        const input = document.createElement('input');
        input.className = 'tab-rename';
        input.value = tab.name;
        input.spellcheck = false;
        label.replaceWith(input);
        input.focus();
        input.select();
        let done = false;
        const finish = (save) => {
            if (done) return;
            done = true;
            const value = input.value;
            if (save) renameTab(id, value);
            else renderTabs();
        };
        input.addEventListener('keydown', (event) => {
            if (event.key === 'Enter') {
                event.preventDefault();
                finish(true);
            } else if (event.key === 'Escape') {
                event.preventDefault();
                finish(false);
            }
        });
        input.addEventListener('blur', () => finish(true));
    }

    function requestCloseTab(id) {
        const tab = getTab(id);
        if (!tab) return;
        if (tab.dirty) {
            askConfirm('「' + tab.name + '」已经修改过了，确定要关闭吗？', () => closeTab(id));
            return;
        }
        closeTab(id);
    }

    function closeTab(id) {
        const index = state.tabs.findIndex((tab) => tab.id === id);
        if (index < 0) return;
        const closing = state.tabs[index];
        if (closing.cm) {
            closing.cm.getWrapperElement().remove();
            closing.cm = null;
        }
        state.tabs.splice(index, 1);
        if (state.compareTabId === id) state.compareTabId = null;

        if (state.activeTabId === id) {
            const next = state.tabs[Math.min(index, state.tabs.length - 1)];
            state.activeTabId = next ? next.id : null;
            showActiveEditor();
        }
        /* 最后一个标签关掉后就是空状态，不再自动补一个文件出来 */
        if (state.split) {
            if (state.compareTabId === state.activeTabId || !getTab(state.compareTabId)) {
                const others = state.tabs.filter((tab) => tab.id !== state.activeTabId);
                state.compareTabId = others.length ? others[0].id : null;
            }
            showCompareEditor();
        } else {
            parkOtherEditors();
        }
        renderTabs();
        renderCompareSelect();
        updateHeaderFileName();
        scheduleSaveTabs();
    }

    function newTab() {
        const tab = createTab(uniqueName('untitled.cpp'), '');
        renderTabs();
        activateTab(tab.id);
        startRename(tab.id);
        scheduleSaveTabs();
    }

    /* 把当前文件重置为内置的示例代码 */
    function loadSampleCode() {
        const tab = getActiveTab();
        if (!tab || !cm) return;
        const apply = () => {
            cm.setValue(DEFAULT_CODE);
            cm.setCursor({ line: 0, ch: 0 });
            cm.focus();
            toast('已把「' + tab.name + '」重置为示例代码', 'ok');
        };
        if (tab.dirty) {
            askConfirm('「' + tab.name + '」已经修改过了，确定要重置为示例代码吗？', apply);
            return;
        }
        apply();
    }

    function switchTabOffset(offset) {
        if (state.tabs.length < 2) return;
        const index = state.tabs.findIndex((tab) => tab.id === state.activeTabId);
        if (index < 0) return;
        const next = (index + offset + state.tabs.length) % state.tabs.length;
        activateTab(state.tabs[next].id);
    }

    /* ------------------------------------------------------------------ */
    /*  左右分栏对比                                                        */
    /* ------------------------------------------------------------------ */
    function toggleSplit(force) {
        const want = typeof force === 'boolean' ? force : !state.split;
        if (want && state.tabs.length < 2) {
            toast('至少要打开两个文件才能分栏对比', 'warn');
            return;
        }
        state.split = want;
        $('editorSplit').classList.toggle('split', want);
        $('colRight').hidden = !want;
        $('splitHandle').hidden = !want;
        $('btnSplit').classList.toggle('active', want);
        if (want) {
            const others = state.tabs.filter((tab) => tab.id !== state.activeTabId);
            if (!getTab(state.compareTabId) || state.compareTabId === state.activeTabId) {
                state.compareTabId = others.length ? others[0].id : null;
            }
            showCompareEditor();
            renderCompareSelect();
        } else {
            cm2 = null;
            parkOtherEditors();
        }
        setTimeout(() => {
            if (cm) cm.refresh();
            if (state.split && cm2) cm2.refresh();
        }, 40);
        scheduleSaveTabs();
    }

    /* ------------------------------------------------------------------ */
    /*  隐藏 / 显示右侧样例侧栏                                              */
    /* ------------------------------------------------------------------ */
    /* 侧栏藏起来之后，编辑区（含分栏后的两栏）要立刻占满整行宽度。
       宽度由 CSS Grid 按百分比算，浏览器自己就会跟着变；
       但 CodeMirror 5 不会自动重新量尺寸，必须手动 refresh() 一次，
       否则编辑器还停在旧宽度，横向滚动条也会不对。 */
    function isSideHidden() {
        return document.body.classList.contains('side-hidden');
    }

    function refreshEditorSizes() {
        /* 等新布局落地之后再量，否则量到的还是旧宽度 */
        requestAnimationFrame(() => {
            if (cm) {
                try { cm.refresh(); } catch (err) { /* ignore */ }
            }
            if (state.split && cm2) {
                try { cm2.refresh(); } catch (err) { /* ignore */ }
            }
            /* PDF 预览是按 window resize 重画的，这里补一个事件让它跟着重排 */
            window.dispatchEvent(new Event('resize'));
        });
    }

    /* 拖动分栏分隔条时用：每帧最多刷新一次，别把主线程塞满 */
    let editorRefreshPending = false;
    function scheduleEditorRefresh() {
        if (editorRefreshPending) return;
        editorRefreshPending = true;
        requestAnimationFrame(() => {
            editorRefreshPending = false;
            if (cm) {
                try { cm.refresh(); } catch (err) { /* ignore */ }
            }
            if (state.split && cm2) {
                try { cm2.refresh(); } catch (err) { /* ignore */ }
            }
        });
    }

    function setSideHidden(hidden, persist) {
        const want = !!hidden;
        state.sideHidden = want;
        document.body.classList.toggle('side-hidden', want);

        const btn = $('btnToggleSide');
        if (btn) {
            btn.classList.toggle('active', want);
            btn.title = want ? '显示右侧样例侧栏 (Alt+H)' : '隐藏右侧样例侧栏 (Alt+H)';
            const text = btn.querySelector('.btn-text');
            if (text) text.textContent = want ? '显示侧栏' : '侧栏';
            const ico = btn.querySelector('.ico');
            if (ico) ico.textContent = want ? '◧' : '◨';
        }

        refreshEditorSizes();
        if (persist !== false) scheduleSaveWorkspace();
        toast(want ? '已隐藏样例侧栏，编辑区占满整屏' : '已显示样例侧栏', 'ok');
    }

    function toggleSide() {
        setSideHidden(!isSideHidden());
    }

    /* 评测 / 运行的结果都显示在侧栏里：侧栏藏着的话，用户会以为按钮没反应，
       所以这两个动作先把侧栏叫出来。 */
    function revealSide() {
        if (isSideHidden()) setSideHidden(false);
    }

    function renderCompareSelect() {
        const select = $('cmpSelect');
        if (!select) return;
        select.innerHTML = '';
        let count = 0;
        state.tabs.forEach((tab) => {
            if (tab.id === state.activeTabId) return;
            count += 1;
            const option = document.createElement('option');
            option.value = tab.id;
            option.textContent = tab.name;
            if (tab.id === state.compareTabId) option.selected = true;
            select.appendChild(option);
        });
        if (!count) {
            const option = document.createElement('option');
            option.textContent = '（没有其它文件）';
            select.appendChild(option);
        } else if (state.compareTabId) {
            select.value = state.compareTabId;
        }
    }

    function setCompareTab(id) {
        if (id === state.activeTabId) return;
        state.compareTabId = id;
        showCompareEditor();
        parkOtherEditors();
        renderCompareSelect();
        scheduleSaveTabs();
    }

    /* 把右栏文件换成当前编辑目标 */
    function swapActiveAndCompare() {
        const compare = getTab(state.compareTabId);
        if (!compare) {
            toast('右栏还没有选择要对比的文件', 'warn');
            return;
        }
        const previous = state.activeTabId;
        state.activeTabId = compare.id;
        state.compareTabId = previous;
        showActiveEditor();
        showCompareEditor();
        renderTabs();
        renderCompareSelect();
        scheduleSaveTabs();
        toast('已把「' + compare.name + '」设为当前编辑目标', 'ok');
    }

    /* 左右两栏滚动位置联动 */
    function syncScroll(source, target) {
        if (!state.split || !state.syncScroll || syncingScroll || !target) return;
        syncingScroll = true;
        const info = source.getScrollInfo();
        const height = info.height - info.clientHeight;
        const ratio = height > 0 ? info.top / height : 0;
        const targetInfo = target.getScrollInfo();
        const targetHeight = targetInfo.height - targetInfo.clientHeight;
        target.scrollTo(null, Math.max(0, ratio * targetHeight));
        syncingScroll = false;
    }

    /* 拖动中间分隔条调整左右比例 */
    function initSplitResize() {
        const handle = $('splitHandle');
        let dragging = false;
        const onMove = (event) => {
            if (!dragging) return;
            const rect = $('editorSplit').getBoundingClientRect();
            if (!rect.width) return;
            const ratio = ((event.clientX - rect.left) / rect.width) * 100;
            const clamped = Math.max(15, Math.min(85, ratio));
            document.documentElement.style.setProperty('--split-left', clamped.toFixed(2) + '%');
            /* CodeMirror 不会自己量宽度：拖动时顺手刷新，两栏才跟得上 */
            scheduleEditorRefresh();
        };
        const onUp = () => {
            dragging = false;
            document.removeEventListener('mousemove', onMove);
            document.removeEventListener('mouseup', onUp);
        };
        handle.addEventListener('mousedown', (event) => {
            dragging = true;
            document.addEventListener('mousemove', onMove);
            document.addEventListener('mouseup', onUp);
            event.preventDefault();
        });
    }

    /* ------------------------------------------------------------------ */
    /*  标签页持久化                                                        */
    /* ------------------------------------------------------------------ */
    function scheduleSaveTabs() {
        if (saveTabsTimer) clearTimeout(saveTabsTimer);
        saveTabsTimer = setTimeout(saveTabs, 400);
        scheduleSaveWorkspace();
    }

    function saveTabs() {
        saveTabsTimer = null;
        try {
            localStorage.setItem(TABS_KEY, JSON.stringify({
                tabs: state.tabs.map((tab) => ({
                    id: tab.id,
                    name: tab.name,
                    content: tab.content,
                    dirty: tab.dirty,
                    view: tab.view,
                    asset: tab.asset
                })),
                activeTabId: state.activeTabId,
                split: state.split,
                compareTabId: state.compareTabId
            }));
        } catch (err) {
            /* 超出本地存储配额时忽略 */
        }
    }

    function restoreTabs(workspace) {
        let saved = null;
        /* 优先用服务端工作区（关掉 exe 也不会丢），其次才用浏览器缓存 */
        if (workspace && Array.isArray(workspace.tabs)) {
            saved = workspace;
        } else {
            try {
                saved = JSON.parse(localStorage.getItem(TABS_KEY) || 'null');
            } catch (err) {
                saved = null;
            }
        }
        if (saved && Array.isArray(saved.tabs) && saved.tabs.length) {
            state.tabs = saved.tabs.map((item) => {
                const id = item.id || nextTabId();
                const match = /^tab-(\d+)$/.exec(id);
                if (match) tabSeq = Math.max(tabSeq, parseInt(match[1], 10));
                return {
                    id: id,
                    name: item.name || 'untitled.cpp',
                    content: typeof item.content === 'string' ? item.content : '',
                    dirty: !!item.dirty,
                    cursor: { line: 0, ch: 0 },
                    scroll: 0,
                    lang: detectLanguage(item.name || 'untitled.cpp'),
                    view: item.view === 'preview' ? 'preview' : 'edit',
                    asset: item.asset || null
                };
            });
            state.activeTabId = state.tabs.some((tab) => tab.id === saved.activeTabId)
                ? saved.activeTabId
                : state.tabs[0].id;
            state.compareTabId = saved.compareTabId || null;
            state.split = !!saved.split && state.tabs.length > 1;
        } else {
            /* 没有任何记录时就是「空的」：不自动塞一个示例文件进来 */
            state.tabs = [];
            state.activeTabId = null;
        }
    }

    /* ------------------------------------------------------------------ */
    /*  工作区持久化：关掉 IDE 也不丢代码                                     */
    /* ------------------------------------------------------------------ */
    const WORKSPACE_KEY = 'cpide.workspace';
    let workspaceTimer = null;
    /* 启动时先把上次的工作区读回来，读完之前不往外写，避免把旧数据覆盖掉 */
    let workspaceReady = false;

    /* 界面上的 C++ 编译选项 */
    function collectCppSettings() {
        return {
            std: $('optStd') ? $('optStd').value : 'c++14',
            warnings: Array.from(document.querySelectorAll('input[data-flag="warning"]:checked'))
                .map((el) => el.value),
            opt: $('optLevel') ? $('optLevel').value : '-O2',
            debug: !!($('optDebug') && $('optDebug').checked),
            static: !!($('optStatic') && $('optStatic').checked),
            sanitize: !!($('optSanitize') && $('optSanitize').checked),
            extra_args: $('optExtra') ? $('optExtra').value.trim() : ''
        };
    }

    /* 把 C++ 编译选项写回界面 */
    function applyCppSettings(settings) {
        if (!settings) return;
        if ($('optStd') && settings.std) $('optStd').value = settings.std;
        if ($('optLevel') && settings.opt) $('optLevel').value = settings.opt;
        if ($('optExtra')) $('optExtra').value = settings.extra_args || '';
        if ($('optDebug')) $('optDebug').checked = !!settings.debug;
        if ($('optStatic')) $('optStatic').checked = !!settings.static;
        if ($('optSanitize')) $('optSanitize').checked = !!settings.sanitize;
        const picked = settings.warnings || [];
        document.querySelectorAll('input[data-flag="warning"]').forEach((el) => {
            el.checked = picked.indexOf(el.value) >= 0;
        });
        updateCommandPreview();
    }

    /* 收集整个工作区：标签页内容 + 界面偏好 + 上一次编译信息 */
    function collectWorkspace() {
        /* 外观这类设置直接读当前生效的值，避免和浏览器缓存不同步 */
        const root = document.documentElement;
        const fontSize = (root.style.getPropertyValue('--editor-font-size') || '13.5px')
            .replace('px', '').trim() || '13.5';
        let mode = 'sample';
        try {
            mode = localStorage.getItem(MODE_KEY) || 'sample';
        } catch (err) { /* ignore */ }
        const bar = $('statusbar');
        return {
            version: 1,
            tabs: state.tabs.map((tab) => ({
                id: tab.id,
                name: tab.name,
                content: tab.content || '',
                dirty: !!tab.dirty,
                view: tab.view,
                asset: tab.asset || null
            })),
            activeTabId: state.activeTabId,
            split: state.split,
            compareTabId: state.compareTabId,
            syncScroll: state.syncScroll,
            settings: {
                theme: state.themePref || 'auto',
                mono: root.getAttribute('data-mono') || 'default',
                fontSize: fontSize,
                mode: mode,
                pythonPath: state.pythonPath,
                cpp: collectCppSettings(),
                statusHidden: isStatusHidden(),
                statusCollapsed: !!(bar && bar.classList.contains('collapsed')),
                sideHidden: state.sideHidden,
                shortcuts: Object.assign({}, state.shortcuts),
                md: {
                    highlight: state.mdOptions.highlight !== false,
                    lineNumbers: !!state.mdOptions.lineNumbers
                }
            },
            compile: state.lastCompile
        };
    }

    /* 防抖保存（改一个字不会马上写盘） */
    function scheduleSaveWorkspace() {
        if (!workspaceReady) return;
        if (workspaceTimer) clearTimeout(workspaceTimer);
        workspaceTimer = setTimeout(saveWorkspace, 600);
    }

    async function saveWorkspace() {
        workspaceTimer = null;
        const data = collectWorkspace();
        try { localStorage.setItem(WORKSPACE_KEY, JSON.stringify(data)); } catch (err) { /* ignore */ }
        try {
            await postJson('/api/workspace', { workspace: data });
        } catch (err) {
            /* 服务器不可用时靠浏览器缓存兜底 */
        }
    }

    /* 读取工作区：优先服务器上的文件，其次浏览器缓存 */
    async function loadWorkspace() {
        try {
            const result = await api('/api/workspace');
            /* 服务器上有记录就以它为准（哪怕记录的是「空的」） */
            if (result && result.ok && result.workspace && Array.isArray(result.workspace.tabs)) {
                return result.workspace;
            }
        } catch (err) { /* ignore */ }
        try {
            const raw = localStorage.getItem(WORKSPACE_KEY);
            if (raw) {
                const data = JSON.parse(raw);
                if (data && Array.isArray(data.tabs)) return data;
            }
        } catch (err) { /* ignore */ }
        return null;
    }

    /* 应用工作区里的界面偏好 */
    function applyWorkspaceSettings(settings) {
        if (!settings) return;
        if (settings.theme) applyTheme(settings.theme);
        /* 顺带写回浏览器缓存，两边保持一致 */
        if (settings.mono) applyMonoFont(settings.mono, true);
        if (settings.fontSize) applyEditorFontSize(settings.fontSize, true);
        if (typeof settings.pythonPath === 'string') {
            state.pythonPath = settings.pythonPath;
            const input = $('optPythonPath');
            if (input) input.value = settings.pythonPath;
        }
        applyCppSettings(settings.cpp);
        if (settings.statusHidden) setStatusHidden(true, false);
        if (typeof settings.statusCollapsed === 'boolean') {
            setStatusCollapsed(settings.statusCollapsed, false);
        }
        if (typeof settings.sideHidden === 'boolean') {
            setSideHidden(settings.sideHidden, false);
        }
        if (settings.shortcuts && typeof settings.shortcuts === 'object') {
            loadShortcuts(settings.shortcuts);
        }
        if (settings.mode) switchMode(settings.mode);
        if (settings.md) {
            state.mdOptions.highlight = settings.md.highlight !== false;
            state.mdOptions.lineNumbers = !!settings.md.lineNumbers;
            const hl = $('optMdHighlight');
            if (hl) hl.checked = state.mdOptions.highlight;
            const ln = $('optMdLineNumbers');
            if (ln) ln.checked = state.mdOptions.lineNumbers;
        }
    }

    /* ------------------------------------------------------------------ */
    /*  导出到电脑                                                          */
    /* ------------------------------------------------------------------ */
    function tabContent(tab) {
        if (!tab) return '';
        if (tab.cm) {
            try { return tab.cm.getValue(); } catch (err) { /* ignore */ }
        }
        return tab.content || '';
    }

    /* 浏览器兜底：直接下载 */
    function downloadBlob(blob, filename) {
        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.download = filename;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        setTimeout(() => URL.revokeObjectURL(url), 2000);
    }

    function downloadText(name, content) {
        downloadBlob(new Blob([content], { type: 'text/plain;charset=utf-8' }), name);
    }

    /* 把当前文件另存到电脑 */
    async function exportCurrentFile() {
        const tab = getActiveTab();
        if (!tab) { toast('没有可导出的文件', 'err'); return; }
        if (tab.lang && tab.lang.kind === 'pdf') {
            toast('PDF 是只读文档，没有可导出的源码', 'err');
            return;
        }
        const name = tab.name || 'untitled.txt';
        const content = tabContent(tab);
        try {
            const result = await postJson('/api/export/file', { name: name, content: content });
            if (result.ok) {
                toast('已导出到 ' + result.path, 'ok');
            } else if (!result.cancelled) {
                toast(result.error || '导出失败', 'err');
            }
        } catch (err) {
            downloadText(name, content);
            toast('已下载 ' + name, 'ok');
        }
    }

    /* 把所有标签页导成一个 zip */
    async function exportAllFiles() {
        const files = state.tabs
            .filter((tab) => !(tab.lang && tab.lang.kind === 'pdf'))
            .map((tab) => ({ name: tab.name, content: tabContent(tab) }));
        if (!files.length) { toast('当前没有可导出的文件', 'err'); return; }
        try {
            const result = await postJson('/api/export/workspace', { files: files });
            if (result.ok) {
                toast('已导出 ' + result.count + ' 个文件到 ' + result.path, 'ok');
            } else if (!result.cancelled) {
                toast(result.error || '导出失败', 'err');
            }
        } catch (err) {
            try {
                const response = await fetch('/api/export/workspace.zip', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ files: files })
                });
                downloadBlob(await response.blob(), 'workspace.zip');
                toast('已导出 ' + files.length + ' 个文件（workspace.zip）', 'ok');
            } catch (err2) {
                toast('导出失败：' + err2.message, 'err');
            }
        }
    }

    /* 重新载入上次的工作区 */
    async function reloadWorkspace() {
        const data = await loadWorkspace();
        if (!data) { toast('没有找到上次的工作区', 'err'); return; }
        applyWorkspaceSettings(data.settings);
        restoreTabs(data);
        showActiveEditor();
        renderTabs();
        renderCompareSelect();
        if (state.split) toggleSplit(true);
        updateHeaderFileName();
        if (data.compile) {
            state.lastCompile = data.compile;
            updateCompileHeader(data.compile);
            renderCompileLog(data.compile);
        }
        toast('已重新载入上次的工作区', 'ok');
        scheduleSaveWorkspace();
    }

    /* ------------------------------------------------------------------ */
    /*  打开本地文件 / 示例文档                                              */
    /* ------------------------------------------------------------------ */
    function base64ToText(b64) {
        try {
            return decodeURIComponent(escape(atob(b64 || '')));
        } catch (err) {
            try {
                return atob(b64 || '');
            } catch (err2) {
                return '';
            }
        }
    }

    /* 用一份文档内容新建标签页（PDF 走资源上传） */
    async function openDocument(name, text, b64, size) {
        const lang = detectLanguage(name);
        try {
            if (lang.kind === 'pdf') {
                const result = await postJson('/api/assets', { name: name, content_b64: b64 });
                if (!result.ok) {
                    toast('打开失败：' + (result.error || '未知错误'), 'err');
                    return;
                }
                const tab = createTab(name, '', {
                    asset: { token: result.token, name: name, size: result.size || size }
                });
                renderTabs();
                activateTab(tab.id);
                toast('已打开 ' + name, 'ok');
                return;
            }
            const content = (text === null || text === undefined)
                ? base64ToText(b64)
                : text;
            const tab = createTab(name, content);
            renderTabs();
            activateTab(tab.id);
            toast('已打开 ' + name, 'ok');
        } catch (err) {
            toast('打开文件失败：' + err.message, 'err');
        }
    }

    async function openLocalFile(file) {
        const name = file.name;
        const lang = detectLanguage(name);
        try {
            if (lang.kind === 'pdf') {
                const b64 = await readFileAsBase64(file);
                await openDocument(name, '', b64, file.size);
                return;
            }
            const text = await file.text();
            await openDocument(name, text, '', file.size);
        } catch (err) {
            toast('打开文件失败：' + err.message, 'err');
        }
    }

    /* 示例文档下拉菜单 */
    function toggleDocMenu() {
        const menu = $('docMenu');
        if (!menu.hidden) {
            menu.hidden = true;
            return;
        }
        const rect = $('btnDemoDocs').getBoundingClientRect();
        menu.style.left = Math.round(rect.left) + 'px';
        menu.style.top = Math.round(rect.bottom + 6) + 'px';
        menu.hidden = false;
    }

    /* 点开一个内置示例文档 */
    async function openDemoDoc(name) {
        try {
            const result = await api('/api/demo-doc/' + encodeURIComponent(name));
            if (!result.ok) {
                toast(result.error || '读取失败', 'err');
                return;
            }
            await openDocument(result.name, null, result.content_b64, result.size);
        } catch (err) {
            toast('读取失败：' + err.message, 'err');
        }
    }

    /* 切换 Markdown 的「源码 / 预览」 */
    function toggleViewMode() {
        const tab = getActiveTab();
        if (!tab || !tab.lang || tab.lang.kind !== 'markdown') return;
        tab.view = tab.view === 'preview' ? 'edit' : 'preview';
        updateViewToggle();
        refreshDocView('left');
        scheduleSaveTabs();
    }

    /* 版本信息（设置 → 关于） */
    async function loadAboutInfo() {
        const box = $('aboutBox');
        if (!box) return;
        try {
            const info = await api('/api/version');
            const rows = [
                ['版本', 'v' + info.version],
                ['构建', info.build || '-'],
                ['运行方式', info.frozen ? '独立 exe' : '源码运行'],
                ['Python', info.python || '-'],
                ['Flask', info.flask || '-'],
                ['编译器', info.compiler_version || '未找到']
            ];
            box.innerHTML = rows.map((row) =>
                '<div class="about-row"><span>' + escapeHtml(row[0]) + '</span>' +
                '<span>' + escapeHtml(row[1]) + '</span></div>'
            ).join('');
        } catch (err) {
            box.innerHTML = '<p class="field-hint">读取版本信息失败：' + escapeHtml(err.message) + '</p>';
        }
    }

    /* 语言表（来自后端） */
    async function loadLanguages() {        try {
            const info = await api('/api/languages');
            (info.languages || []).forEach((lang) => {
                state.languages[lang.id] = lang;
            });
            state.pythonInterpreter = info.python_interpreter || '';
            state.tabs.forEach((tab) => {
                tab.lang = detectLanguage(tab.name);
            });
            const tab = getActiveTab();
            if (tab) applyTabLanguage(tab);
        } catch (err) {
            /* 用内置的兜底表即可 */
        }
    }

    /* ------------------------------------------------------------------ */
    /*  浮动确认条                                                          */
    /* ------------------------------------------------------------------ */
    let confirmAction = null;

    function askConfirm(text, action) {
        $('confirmText').textContent = text;
        $('confirmBar').hidden = false;
        confirmAction = action;
    }

    function closeConfirm(accept) {
        $('confirmBar').hidden = true;
        const action = confirmAction;
        confirmAction = null;
        if (accept && action) action();
    }

    /* ------------------------------------------------------------------ */
    /*  编译环境设置                                                        */
    /* ------------------------------------------------------------------ */
    function currentSettings() {
        return {
            std: $('optStd').value,
            warnings: Array.from(document.querySelectorAll('input[data-flag="warning"]:checked'))
                .map((el) => el.value),
            opt: $('optLevel').value,
            debug: $('optDebug').checked,
            static: $('optStatic').checked,
            sanitize: $('optSanitize').checked,
            extra_args: $('optExtra').value.trim(),
            python_path: state.pythonPath
        };
    }

    /* 设置抽屉按当前语言切换：Python 只关心解释器，C++ 只关心编译选项 */
    function applyLanguageSettings() {
        const lang = activeLanguage();
        const cppBox = $('secCppEnv');
        const pyBox = $('secPythonEnv');
        if (cppBox) cppBox.hidden = lang.id !== 'cpp';
        if (pyBox) pyBox.hidden = lang.id !== 'python';
        const info = $('pythonInterpreterInfo');
        if (info) {
            const exe = state.pythonInterpreter || '';
            info.textContent = exe ? ('当前使用的解释器：' + exe) : '';
        }
    }

    function currentLimits() {
        return {
            time_limit: parseInt($('optTimeLimit').value, 10) || 1000,
            memory_limit: parseInt($('optMemoryLimit').value, 10) || 256
        };
    }

    function updateCommandPreview() {
        const settings = currentSettings();
        const parts = ['g++', '-std=' + settings.std];
        const warningLabels = {
            wall: '-Wall', wextra: '-Wextra', wshadow: '-Wshadow',
            wconversion: '-Wconversion', wpedantic: '-Wpedantic', wunused: '-Wunused'
        };
        settings.warnings.forEach((w) => parts.push(warningLabels[w] || w));
        parts.push(settings.opt);
        if (settings.debug) parts.push('-g');
        if (settings.static) parts.push('-static');
        if (settings.sanitize) parts.push('-fsanitize=address,undefined');
        if (settings.extra_args) parts.push(settings.extra_args);
        parts.push('main.cpp', '-o', 'main.exe');
        $('commandPreview').textContent = parts.join(' ');
    }

    /* ------------------------------------------------------------------ */
    /*  底部编译信息                                                        */
    /* ------------------------------------------------------------------ */
    function setCompileDot(kind) {
        const dot = $('compileDot');
        dot.className = 'dot' + (kind ? ' ' + kind : '');
    }

    function renderCompileLog(result) {
        const log = $('compileLog');
        log.innerHTML = '';

        if (!result) {
            log.innerHTML = '<p class="empty-hint">点击「编译」按钮开始编译，编译输出、错误与警告会显示在这里。点击错误可以跳转到对应行。</p>';
            return;
        }

        const diagnostics = result.diagnostics || [];
        if (diagnostics.length) {
            diagnostics.forEach((diag) => {
                const row = document.createElement('div');
                row.className = 'diag-row ' + diag.severity;
                const loc = document.createElement('span');
                loc.className = 'diag-loc';
                loc.textContent = diag.file
                    ? (diag.file.split(/[\\/]/).pop() + ':' + (diag.line || 0) + (diag.col ? ':' + diag.col : ''))
                    : '—';
                const msg = document.createElement('span');
                msg.className = 'diag-msg';
                msg.textContent = diag.message;
                row.appendChild(loc);
                row.appendChild(msg);
                if (diag.line) {
                    row.classList.add('log-clickable');
                    row.title = '点击跳转到第 ' + diag.line + ' 行';
                    row.addEventListener('click', () => {
                        cm.setCursor({ line: diag.line - 1, ch: Math.max(0, (diag.col || 1) - 1) });
                        cm.focus();
                        cm.scrollIntoView({ line: diag.line - 1, ch: 0 }, 120);
                    });
                }
                log.appendChild(row);
            });
        }

        const raw = ((result.stderr || '') + (result.stdout ? '\n' + result.stdout : '')).trim();
        if (raw) {
            const pre = document.createElement('pre');
            pre.style.margin = '10px 0 0';
            pre.textContent = raw;
            log.appendChild(pre);
        }
        if (!diagnostics.length && !raw) {
            const p = document.createElement('p');
            p.className = 'log-ok';
            p.textContent = '编译成功，没有产生任何警告或错误。';
            log.appendChild(p);
        }
    }

    function updateCompileHeader(result) {
        const status = $('compileStatus');
        const time = $('compileTime');
        const counts = $('compileCounts');
        if (!result) {
            status.className = 'chip';
            status.textContent = '未编译';
            time.textContent = '';
            counts.textContent = '';
            $('compileCommand').textContent = '';
            flashRestoreButton();
            return;
        }
        if (result.ok) {
            status.className = 'chip ok';
            status.textContent = '编译成功';
            setCompileDot('ok');
        } else {
            status.className = 'chip err';
            status.textContent = result.message || '编译失败';
            setCompileDot('err');
        }
        time.textContent = '耗时 ' + result.duration_ms + ' ms';
        const errors = result.errors || 0;
        const warnings = result.warnings || 0;
        counts.innerHTML = '';
        if (errors) {
            const chip = document.createElement('span');
            chip.className = 'chip err';
            chip.textContent = errors + ' 个错误';
            counts.appendChild(chip);
        }
        if (warnings) {
            const chip = document.createElement('span');
            chip.className = 'chip warn';
            chip.textContent = warnings + ' 个警告';
            counts.appendChild(chip);
        }
        $('compileCommand').textContent = result.command_line || (result.command || []).join(' ') || '';
        flashRestoreButton();
    }

    /* ------------------------------------------------------------------ */
    /*  编译                                                                */
    /* ------------------------------------------------------------------ */
    /* 一个文件都没打开时，编译 / 运行 / 评测这些操作先给个提示 */
    function requireCode(actionName) {
        if (cm) return cm.getValue();
        toast('先新建或打开一个文件再' + (actionName || '操作'), 'warn');
        return null;
    }

    async function compileCode() {
        const btn = $('btnCompile');
        const lang = activeLanguage();
        if (!lang.runnable) {
            toast('「' + lang.name + '」文件不支持编译', 'warn');
            return;
        }
        const code = requireCode('编译');
        if (code === null) return;
        btn.disabled = true;
        $('compileStatus').className = 'chip warn';
        $('compileStatus').textContent = '编译中…';
        setCompileDot('busy');
        try {
            const result = await postJson('/api/compile', {
                code: code,
                language: activeLanguage().id,
                settings: currentSettings()
            });
            result.command_line = result.command_line || (result.command || []).join(' ');
            if (result.ok) {
                state.sessionId = result.session_id;
                state.dirty = false;
                $('dirtyBadge').hidden = true;
                const tab = getActiveTab();
                if (tab) {
                    tab.dirty = false;
                    const dot = document.querySelector(
                        '.code-tab[data-tab-id="' + tab.id + '"] .tab-dirty');
                    if (dot) dot.hidden = true;
                }
            }
            updateCompileHeader(result);
            renderCompileLog(result);
            /* 记下这次的编译信息，下次打开 IDE 还能看到 */
            state.lastCompile = {
                ok: !!result.ok,
                message: result.message || '',
                stdout: result.stdout || '',
                stderr: result.stderr || '',
                diagnostics: result.diagnostics || [],
                errors: result.errors || 0,
                warnings: result.warnings || 0,
                duration_ms: result.duration_ms || 0,
                command_line: result.command_line || '',
                language: result.language || activeLanguage().id,
                at: Date.now()
            };
            scheduleSaveWorkspace();
            if (result.ok) {
                toast('编译成功（' + result.duration_ms + ' ms）', 'ok');
            } else {
                // 编译失败时自动展开编译信息区，否则错误藏在折叠的细条里看不到
                if ($('statusbar').classList.contains('collapsed')) {
                    setStatusCollapsed(false, true);
                }
                toast(result.message || '编译失败', 'err');
            }
            return result;
        } catch (err) {
            toast('编译请求失败：' + err.message, 'err');
            setCompileDot('err');
            return null;
        } finally {
            btn.disabled = false;
        }
    }

    /* ------------------------------------------------------------------ */
    /*  运行单个样例                                                        */
    /* ------------------------------------------------------------------ */
    /* 「编译并运行」：先编译，编译通过再跑当前样例；
       编译失败就不跑，错误信息留在编译信息区里。 */
    async function compileAndRun() {
        const result = await compileCode();
        if (!result) return;
        if (!result.ok) {
            toast('编译失败，已取消运行', 'err');
            return;
        }
        switchMode('sample');
        await runSample();
    }

    async function runSample() {
        const btn = $('btnSampleRun');
        const lang = activeLanguage();
        if (!lang.runnable) {
            toast('「' + lang.name + '」文件不支持运行', 'warn');
            return;
        }
        /* 结果显示在侧栏里，侧栏藏着的话先把它叫出来 */
        revealSide();
        const code = requireCode('运行');
        if (code === null) return;
        btn.disabled = true;
        const resultBox = $('sampleResult');
        resultBox.textContent = '运行中…';
        try {
            const limits = currentLimits();
            const result = await postJson('/api/run', {
                code: code,
                language: activeLanguage().id,
                session_id: state.sessionId,
                /* 把编译选项一起带上：运行用的就是你在「设置」里选的那套标准与警告等级，
                   并且和「编译」按钮算出的源码哈希一致时可以直接复用刚编译好的可执行文件，
                   不必再编一遍。 */
                settings: currentSettings(),
                input: $('sampleInput').value,
                expected: $('sampleExpected').value,
                checker: $('optChecker').value,
                time_limit: limits.time_limit,
                memory_limit: limits.memory_limit
            });
            if (result.session_id) state.sessionId = result.session_id;

            if (result.status === 'compile_error') {
                resultBox.textContent = '编译错误';
                resultBox.style.color = 'var(--danger)';
                updateCompileHeader(result.compile);
                renderCompileLog(result.compile);
                toast('编译失败，无法运行', 'err');
                return;
            }

            // 程序实际输出单独显示在一个框里
            const sample = state.samples[state.activeSample];
            if (sample) {
                sample.output = result.stdout || '';
                sample.stderr = result.stderr || '';
            }
            showSampleOutput(result.stdout || '', result.stderr || '');

            const ok = result.status === 'accept';
            resultBox.style.color = ok ? 'var(--success)' : 'var(--danger)';
            resultBox.textContent = (ok ? '✓ ' : '✗ ') + result.status_label +
                ' · ' + formatTime(result.time_ms) + ' · ' + formatMemory(result.memory_kb);
            if (sample) {
                sample.verdict = ok ? '✓' : '✗';
                renderSamples();
            }
            if (result.compile) {
                updateCompileHeader(result.compile);
                renderCompileLog(result.compile);
            }
            toast('运行结束：' + result.status_label, ok ? 'ok' : 'warn');
        } catch (err) {
            resultBox.textContent = '运行失败';
            resultBox.style.color = 'var(--danger)';
            toast('运行失败：' + err.message, 'err');
        } finally {
            btn.disabled = false;
        }
    }

    /* ------------------------------------------------------------------ */
    /*  上传文件                                                            */
    /* ------------------------------------------------------------------ */
    function readFileAsBase64(file) {
        return new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onload = () => {
                const result = String(reader.result || '');
                const comma = result.indexOf(',');
                resolve(comma >= 0 ? result.slice(comma + 1) : '');
            };
            reader.onerror = () => reject(reader.error || new Error('读取失败'));
            reader.readAsDataURL(file);
        });
    }

    async function addFiles(fileList) {
        const list = Array.from(fileList || []);
        if (!list.length) return;
        const task = (async () => {
            for (const file of list) {
                try {
                    const b64 = await readFileAsBase64(file);
                    state.files.set(file.name, { name: file.name, b64: b64, size: file.size });
                } catch (err) {
                    toast('读取文件失败：' + file.name, 'err');
                }
            }
            renderFileChips();
            const cfg = Array.from(state.files.keys()).find((n) => /\.(cfg|ini|conf)$/i.test(n));
            if (cfg) {
                try {
                    const text = atob(state.files.get(cfg).b64);
                    $('configText').value = text;
                } catch (err) { /* ignore */ }
            }
            await scanUploads();
            toast('已载入 ' + list.length + ' 个文件', 'ok');
        })();
        fileLoadTask = task;
        return task;
    }

    function renderFileChips() {
        const box = $('fileChips');
        box.innerHTML = '';
        state.files.forEach((entry, name) => {
            const chip = document.createElement('span');
            chip.className = 'file-chip';
            chip.textContent = name + ' (' + formatBytes(entry.size) + ')';
            const del = document.createElement('button');
            del.textContent = '✕';
            del.title = '移除';
            del.addEventListener('click', () => {
                state.files.delete(name);
                renderFileChips();
            });
            chip.appendChild(del);
            box.appendChild(chip);
        });
    }

    /* 载入内置的示例测试集，方便快速体验评测流程 */
    function loadDemoTests() {
        const btn = $('btnLoadDemo');
        btn.disabled = true;
        const task = (async () => {
            try {
                const result = await api('/api/demo-tests');
                (result.files || []).forEach((file) => {
                    state.files.set(file.name, {
                        name: file.name,
                        b64: file.content_b64,
                        size: file.size || 0
                    });
                });
                if (result.config) $('configText').value = result.config;
                renderFileChips();
                await scanUploads();
                switchMode('judge');
                toast('已载入 ' + (result.files || []).length + ' 个示例测试文件', 'ok');
            } catch (err) {
                toast('载入示例测试集失败：' + err.message, 'err');
            } finally {
                btn.disabled = false;
            }
        })();
        fileLoadTask = task;
        return task;
    }

    /* ------------------------------------------------------------------ */
    /*  评测                                                                */
    /* ------------------------------------------------------------------ */
    const STATUS_CLASS = {
        accept: 'ok',
        wrong_answer: 'err',
        presentation_error: 'warn',
        time_limit_exceeded: 'warn',
        memory_limit_exceeded: 'warn',
        runtime_error: 'err',
        output_limit_exceeded: 'warn',
        unknown_error: 'err'
    };

    function renderJudge(result) {
        state.lastJudge = result;
        const summaryBox = $('judgeSummary');
        const list = $('pointList');
        summaryBox.innerHTML = '';
        list.innerHTML = '';

        if (result.error) {
            list.innerHTML = '<p class="empty-hint" style="color:var(--danger)">' +
                escapeHtml(result.error) + '</p>';
            return;
        }

        const summary = result.summary || { total: 0, accept: 0, failed: 0 };
        const chip = (text, cls) => {
            const el = document.createElement('span');
            el.className = 'chip' + (cls ? ' ' + cls : '');
            el.textContent = text;
            summaryBox.appendChild(el);
        };
        chip('共 ' + summary.total + ' 个测试点');
        chip(summary.accept + ' 个通过', 'ok');
        if (summary.failed) chip(summary.failed + ' 个未通过', 'err');
        if (result.warnings && result.warnings.length) {
            chip(result.warnings.length + ' 条提示', 'warn');
        }
        const checkerInfo = result.checker || {};
        if (checkerInfo.enabled) {
            chip('自定义 Checker: ' + (checkerInfo.source || '内置'), 'ok');
        }

        (result.points || []).forEach((point) => {
            const el = document.createElement('div');
            el.className = 'point';
            const cls = STATUS_CLASS[point.status] || '';
            el.innerHTML =
                '<div class="point-head">' +
                '<span class="point-idx">' + point.index + '</span>' +
                '<span class="point-name">' + escapeHtml(point.name) +
                ' <small style="color:var(--text-faint)">' + escapeHtml(point.input_file) + '</small></span>' +
                '<span class="point-metrics">' +
                '<span>' + formatTime(point.time_ms) + '</span>' +
                '<span>' + formatMemory(point.memory_kb) + '</span>' +
                '</span>' +
                '<span class="point-status ' + cls + '" style="color:' +
                (cls === 'ok' ? 'var(--success)' : cls === 'err' ? 'var(--danger)' : 'var(--warning)') +
                '">' + escapeHtml(point.status_label) + '</span>' +
                '</div>' +
                '<div class="point-body">' +
                '<div class="point-msg">' + escapeHtml(point.message || '') + '</div>' +
                '<div class="grid2">' +
                '<div><div class="section-title">程序输出</div><textarea readonly>' +
                escapeHtml(point.output || '') + '</textarea></div>' +
                '<div><div class="section-title">期望输出</div><textarea readonly>' +
                escapeHtml(point.expected || '') + '</textarea></div>' +
                '</div>' +
                (point.diff ? '<pre>' + escapeHtml(point.diff) + '</pre>' : '') +
                (point.stderr ? '<pre>' + escapeHtml(point.stderr) + '</pre>' : '') +
                '</div>';

            const head = el.querySelector('.point-head');
            head.addEventListener('click', () => el.classList.toggle('open'));
            list.appendChild(el);
        });
    }

    async function judgeAll() {
        const btn = $('btnJudge');
        const lang = activeLanguage();
        if (!lang.runnable) {
            toast('「' + lang.name + '」文件不支持评测', 'warn');
            return;
        }
        /* 评测结果也在侧栏里 */
        revealSide();
        const code = requireCode('评测');
        if (code === null) return;
        btn.disabled = true;
        $('judgeSummary').innerHTML = '<span class="chip warn">评测中…</span>';

        // 文件可能还在读取，先等它完成，避免漏掉刚选中的数据
        try {
            await fileLoadTask;
        } catch (err) { /* ignore */ }

        const files = [];
        state.files.forEach((entry) => files.push({ name: entry.name, content_b64: entry.b64 }));

        try {
            const result = await postJson('/api/judge', {
                code: code,
                language: activeLanguage().id,
                settings: currentSettings(),
                config: $('configText').value,
                checker: $('optChecker').value,
                checker_code: checkerCodeFromEditor(),
                files: files
            });
            if (result.compile) {
                result.compile.command_line = result.compile.command_line ||
                    (result.compile.command || []).join(' ');
                updateCompileHeader(result.compile);
                renderCompileLog(result.compile);
            }
            if (result.session_id) state.sessionId = result.session_id;
            renderJudge(result);
            if (result.error) {
                toast(result.error, 'err');
            } else {
                const s = result.summary || {};
                toast('评测完成：' + s.accept + '/' + s.total + ' 通过', s.failed ? 'warn' : 'ok');
            }
        } catch (err) {
            $('judgeSummary').innerHTML = '';
            $('pointList').innerHTML = '<p class="empty-hint" style="color:var(--danger)">' +
                escapeHtml(err.message) + '</p>';
            toast('评测失败：' + err.message, 'err');
        } finally {
            btn.disabled = false;
        }
    }

    /* ------------------------------------------------------------------ */
    /*  自定义 checker（testlib）                                            */
    /* ------------------------------------------------------------------ */

    /* 编辑器里名为 checker.cpp 的标签页内容，会作为自定义 checker 源码 */
    function checkerCodeFromEditor() {
        const tab = state.tabs.find((item) => /^checker\.(cpp|cc|cxx)$/i.test(item.name));
        return tab ? (tab.content || '') : '';
    }

    /* 比较方式选了 custom 时，把 checker 的来源说清楚 */
    function updateCheckerHint() {
        const hint = $('checkerHint');
        if (!hint) return;
        if ($('optChecker').value === 'custom') {
            hint.innerHTML = checkerCodeFromEditor()
                ? '将使用编辑器中 <code>checker.cpp</code> 标签页的内容' +
                  '（上传数据里若也有 checker.cpp，则优先用上传的那份）。'
                : '将使用上传数据里的 <code>checker.cpp</code>。' +
                  '若上传数据里没有，请在编辑器中新建一个名为 <code>checker.cpp</code> 的标签页。';
        } else {
            hint.innerHTML = '选择「自定义 Checker」时，IDE 会使用上传数据里的 <code>checker.cpp</code>，' +
                '或编辑器中名为 <code>checker.cpp</code> 的标签页内容。';
        }
    }

    async function loadTestlibInfo() {
        try {
            const info = await api('/api/testlib');
            state.testlib = info;
            const version = info.version ? ('v' + info.version) : '未检测到';
            $('testlibChip').textContent = 'testlib ' + version;
            $('testlibVersionInline').textContent = version;
            return info;
        } catch (err) {
            return null;
        }
    }

    /* 上传数据后扫描一遍，看看里面有没有 checker.cpp / testlib.h */
    async function scanUploads() {
        const files = [];
        state.files.forEach((entry) => files.push({ name: entry.name, content_b64: entry.b64 }));
        if (!files.length) {
            updateCheckerStatus(null);
            return;
        }
        try {
            const result = await postJson('/api/upload-scan', { files: files });
            state.checkerScan = result;
            updateCheckerStatus(result);
        } catch (err) {
            /* 扫描失败不影响评测 */
        }
    }

    function updateCheckerStatus(scan) {
        const box = $('checkerStatus');
        if (!box) return;
        const tip = '把 <code>checker.cpp</code> 直接放进 zip 里上传即可自动启用；' +
            '内置 testlib，无需再单独上传库文件。';
        if (!scan) {
            box.classList.remove('found');
            box.innerHTML = tip;
            return;
        }
        if (scan.checker) {
            box.classList.add('found');
            box.innerHTML = '已识别 <code>' + escapeHtml(scan.checker) + '</code>，' +
                '评测时会自动使用自定义 Checker。' +
                (scan.testlib ? '（上传数据自带 testlib.h，优先使用）' : '（使用内置 testlib）');
            $('optChecker').value = 'custom';
            return;
        }
        box.classList.remove('found');
        box.innerHTML = (scan.testlib ? '上传数据中自带 <code>testlib.h</code>。' : '') + tip;
    }

    /* 载入内置的示例测试包（里面自带 checker.cpp） */
    function loadDemoCheckerArchive() {
        const btn = $('btnDemoChecker');
        btn.disabled = true;
        const task = (async () => {
            try {
                const result = await api('/api/demo-checker-archive');
                if (!result.ok) {
                    toast(result.error || '没有找到示例测试包', 'err');
                    return;
                }
                state.files.clear();
                state.files.set(result.name, {
                    name: result.name,
                    b64: result.content_b64,
                    size: result.size || 0
                });
                renderFileChips();
                await scanUploads();
                switchMode('judge');
                toast('已载入自带 checker.cpp 的示例测试包', 'ok');
            } catch (err) {
                toast('载入示例测试包失败：' + err.message, 'err');
            } finally {
                btn.disabled = false;
            }
        })();
        fileLoadTask = task;
        return task;
    }

    /* 新建（或覆盖）一个 checker.cpp 标签页，填入内置模板 */
    async function insertCheckerTemplate() {
        const info = state.testlib || await loadTestlibInfo();
        const template = (info && info.template) || '';
        if (!template) {
            toast('没有找到 checker 模板', 'err');
            return;
        }
        const existing = state.tabs.find((tab) => tab.name === 'checker.cpp');
        if (existing) {
            activateTab(existing.id);
            cm.setValue(template);      // 触发 change 处理器：更新内容并标记已修改
            renderTabs();
            toast('已把 checker 模板写入 checker.cpp', 'ok');
            return;
        }
        const tab = createTab('checker.cpp', template, { dirty: true });
        renderTabs();
        activateTab(tab.id);
        toast('已新建 checker.cpp 标签页', 'ok');
    }

    /* 在内置编辑器里浏览 testlib.h */
    async function viewTestlib() {
        try {
            const existing = state.tabs.find((tab) => tab.name === 'testlib.h');
            if (existing) {
                activateTab(existing.id);
                return;
            }
            const result = await api('/api/testlib-source?mode=json');
            const source = result.source || '';
            const tab = createTab('testlib.h', source);
            renderTabs();
            activateTab(tab.id);
            toast('已打开 testlib.h（' + Math.round(source.length / 1024) + ' KB）', 'ok');
        } catch (err) {
            toast('读取 testlib.h 失败：' + err.message, 'err');
        }
    }

    function downloadTestlib() {
        const link = document.createElement('a');
        link.href = '/api/testlib-source';
        link.download = 'testlib.h';
        document.body.appendChild(link);
        link.click();
        link.remove();
    }

    /* ------------------------------------------------------------------ */
    /*  样例测试                                                            */
    /* ------------------------------------------------------------------ */
    function renderSamples() {
        const list = $('sampleList');
        list.innerHTML = '';
        state.samples.forEach((sample, index) => {
            const chip = document.createElement('span');
            chip.className = 'sample-chip' + (index === state.activeSample ? ' active' : '');
            const label = document.createElement('span');
            label.textContent = sample.name;
            chip.appendChild(label);
            if (sample.verdict) {
                const v = document.createElement('span');
                v.className = 'verdict';
                v.textContent = sample.verdict;
                chip.appendChild(v);
            }
            chip.addEventListener('click', () => selectSample(index));
            list.appendChild(chip);
        });
    }

    function selectSample(index) {
        state.activeSample = index;
        const sample = state.samples[index];
        if (!sample) return;
        $('sampleInput').value = sample.input || '';
        $('sampleExpected').value = sample.expected || '';
        $('sampleResult').textContent = '';
        showSampleOutput(sample.output || '', sample.stderr || '');
        renderSamples();
    }

    /* 显示样例运行时程序的实际输出 */
    function showSampleOutput(stdout, stderr) {
        $('sampleOutput').value = stdout || '';
        const hasStderr = !!(stderr && stderr.trim());
        $('sampleStderr').value = stderr || '';
        $('stderrBox').hidden = !hasStderr;
    }

    async function loadSamples() {
        try {
            const result = await api('/api/samples');
            state.samples = (result.samples || []).map((s) => ({
                name: s.name, input: s.input, expected: s.expected
            }));
            renderSamples();
            if (state.samples.length) selectSample(0);
        } catch (err) {
            toast('载入样例失败：' + err.message, 'err');
        }
    }

    function addSample() {
        state.samples.push({ name: '样例 ' + (state.samples.length + 1), input: '', expected: '' });
        renderSamples();
        selectSample(state.samples.length - 1);
    }

    function deleteSample() {
        if (state.activeSample < 0) return;
        state.samples.splice(state.activeSample, 1);
        state.activeSample = Math.min(state.activeSample, state.samples.length - 1);
        renderSamples();
        if (state.activeSample >= 0) selectSample(state.activeSample);
        else {
            $('sampleInput').value = '';
            $('sampleExpected').value = '';
        }
    }

    function persistSampleEdits() {
        if (state.activeSample < 0) return;
        state.samples[state.activeSample].input = $('sampleInput').value;
        state.samples[state.activeSample].expected = $('sampleExpected').value;
    }

    /* ------------------------------------------------------------------ */
    /*  插入代码                                                            */
    /* ------------------------------------------------------------------ */
    async function loadSnippets() {
        try {
            const result = await api('/api/snippets');
            state.snippets = result.snippets || [];
            state.positions = result.positions || {};
            renderSnippets();
        } catch (err) {
            toast('载入代码片段失败：' + err.message, 'err');
        }
    }

    function renderSnippets() {
        const box = $('snippetList');
        box.innerHTML = '';
        state.snippets.forEach((snippet) => {
            const el = document.createElement('div');
            el.className = 'snippet';
            el.innerHTML =
                '<div class="snippet-info">' +
                '<div class="snippet-name">' + escapeHtml(snippet.name) +
                (snippet.builtin ? ' <span class="chip" style="font-size:9.5px">内置</span>' : '') +
                '</div>' +
                '<div class="snippet-desc">' + escapeHtml(snippet.description || '') + '</div>' +
                '</div>';
            const btns = document.createElement('div');
            btns.className = 'snippet-btns';
            const insertBtn = document.createElement('button');
            insertBtn.className = 'btn small';
            insertBtn.textContent = '插入';
            insertBtn.addEventListener('click', () => insertSnippet(snippet.id));
            btns.appendChild(insertBtn);
            if (!snippet.builtin) {
                const editBtn = document.createElement('button');
                editBtn.className = 'icon-btn small';
                editBtn.textContent = '✎';
                editBtn.title = '编辑';
                editBtn.addEventListener('click', () => editSnippet(snippet));
                btns.appendChild(editBtn);
                const delBtn = document.createElement('button');
                delBtn.className = 'icon-btn small';
                delBtn.textContent = '🗑';
                delBtn.title = '删除';
                delBtn.addEventListener('click', () => deleteSnippet(snippet.id));
                btns.appendChild(delBtn);
            }
            el.appendChild(btns);
            box.appendChild(el);
        });
    }

    async function insertSnippet(snippetId) {
        const code = requireCode('插入代码');
        if (code === null) return;
        try {
            const result = await postJson('/api/insert', {
                code: code,
                snippet_id: snippetId,
                position: $('insertPosition').value
            });
            if (result.code !== undefined) {
                cm.setValue(result.code);
                cm.focus();
                toast('已插入代码片段', 'ok');
            }
        } catch (err) {
            toast('插入失败：' + err.message, 'err');
        }
    }

    function editSnippet(snippet) {
        state.editingSnippetId = snippet.id;
        $('snippetEditorBox').hidden = false;
        $('snippetName').value = snippet.name;
        $('snippetDesc').value = snippet.description || '';
        $('snippetCode').value = snippet.code || '';
    }

    function newSnippet() {
        state.editingSnippetId = null;
        $('snippetEditorBox').hidden = false;
        $('snippetName').value = '';
        $('snippetDesc').value = '';
        $('snippetCode').value = '';
        $('snippetName').focus();
    }

    async function saveSnippet() {
        const name = $('snippetName').value.trim();
        const code = $('snippetCode').value;
        if (!name || !code.trim()) {
            toast('请填写片段名称与代码', 'warn');
            return;
        }
        const id = state.editingSnippetId || ('user-' + Date.now().toString(36));
        try {
            await postJson('/api/snippets', {
                id: id, name: name,
                description: $('snippetDesc').value.trim(),
                code: code,
                position: $('insertPosition').value
            });
            $('snippetEditorBox').hidden = true;
            state.editingSnippetId = null;
            await loadSnippets();
            toast('代码片段已保存', 'ok');
        } catch (err) {
            toast('保存失败：' + err.message, 'err');
        }
    }

    async function deleteSnippet(id) {
        try {
            await api('/api/snippets/' + encodeURIComponent(id), { method: 'DELETE' });
            await loadSnippets();
            toast('代码片段已删除', 'ok');
        } catch (err) {
            toast('删除失败：' + err.message, 'err');
        }
    }

    /* ------------------------------------------------------------------ */
    /*  查找替换                                                            */
    /* ------------------------------------------------------------------ */
    const WORD = 'A-Za-z0-9_\\u00C0-\\uFFFF';

    function escapeRegExp(text) {
        return text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    }

    function buildQuery() {
        const find = $('searchFind').value;
        if (!find) return null;
        const flags = $('searchCase').checked ? 'g' : 'gi';
        if ($('searchRegex').checked) {
            try {
                return new RegExp(find, flags);
            } catch (err) {
                toast('正则表达式无效：' + err.message, 'err');
                return null;
            }
        }
        let source = escapeRegExp(find);
        if ($('searchWord').checked) {
            source = '(?<![' + WORD + '])' + source + '(?![' + WORD + '])';
        }
        return new RegExp(source, flags);
    }

    function findNext(direction) {
        const query = buildQuery();
        if (!query) {
            $('searchStatus').textContent = '请输入查找内容';
            return;
        }
        let cursor = cm.getSearchCursor(query, cm.getCursor());
        if (direction < 0) {
            if (!cursor.find(true)) {
                cursor = cm.getSearchCursor(query, { line: cm.lastLine() });
                if (!cursor.find(true)) {
                    $('searchStatus').textContent = '没有更多匹配';
                    return;
                }
            }
        } else if (!cursor.findNext()) {
            cursor = cm.getSearchCursor(query, { line: 0, ch: 0 });
            if (!cursor.findNext()) {
                $('searchStatus').textContent = '没有更多匹配';
                return;
            }
        }
        cm.setSelection(cursor.from(), cursor.to());
        cm.scrollIntoView(cursor.from(), 120);
        $('searchStatus').textContent = '已定位到第 ' + (cursor.from().line + 1) + ' 行';
    }

    function countMatches() {
        const query = buildQuery();
        if (!query) return 0;
        let count = 0;
        const cursor = cm.getSearchCursor(query, { line: 0, ch: 0 });
        while (cursor.findNext()) count++;
        return count;
    }

    function findAll() {
        const query = buildQuery();
        if (!query) return;
        const marks = [];
        const cursor = cm.getSearchCursor(query, { line: 0, ch: 0 });
        while (cursor.findNext()) {
            marks.push(cursor.from());
            if (marks.length > 5000) break;
        }
        cm.operation(() => {
            cm.setSelections(marks, marks.map(() => null));
        });
        $('searchStatus').textContent = '共找到 ' + marks.length + ' 处匹配';
    }

    function replaceAll() {
        const query = buildQuery();
        const replacement = $('searchReplace').value;
        if (!query) {
            toast('请输入查找内容', 'warn');
            return;
        }
        let count = 0;
        cm.operation(() => {
            const cursor = cm.getSearchCursor(query, { line: 0, ch: 0 });
            while (cursor.findNext()) {
                cursor.replace(replacement);
                count++;
                if (count > 20000) break;
            }
        });
        $('searchStatus').textContent = '已替换 ' + count + ' 处';
        toast('已替换 ' + count + ' 处', 'ok');
    }

    function replaceCurrent() {
        const query = buildQuery();
        const replacement = $('searchReplace').value;
        if (!query) {
            toast('请输入查找内容', 'warn');
            return;
        }
        const selection = cm.getSelection();
        if (selection && query.test(selection)) {
            cm.replaceSelection(replacement, 'around');
            $('searchStatus').textContent = '已替换 1 处';
            return;
        }
        findNext(1);
        const cursor = cm.getSearchCursor(query, cm.getCursor());
        if (cursor.findNext()) {
            cursor.replace(replacement);
            $('searchStatus').textContent = '已替换 1 处';
        } else {
            $('searchStatus').textContent = '没有匹配项';
        }
    }

    function replaceInSelection() {
        const query = buildQuery();
        const replacement = $('searchReplace').value;
        if (!query) {
            toast('请输入查找内容', 'warn');
            return;
        }
        const from = cm.indexFromPos(cm.getCursor('from'));
        const to = cm.indexFromPos(cm.getCursor('to'));
        if (from === to) {
            toast('请先选中一段内容', 'warn');
            return;
        }
        const text = cm.getRange(cm.getCursor('from'), cm.getCursor('to'));
        const replaced = text.replace(query, replacement);
        cm.replaceSelection(replaced, 'around');
        $('searchStatus').textContent = '已在选中内容中完成替换';
    }

    /* ------------------------------------------------------------------ */
    /*  格式化                                                              */
    /* ------------------------------------------------------------------ */
    /* 统一的格式化请求：预览视图和直接应用都走这里 */
    function requestFormat(code) {
        return postJson('/api/format', {
            code: code,
            options: {
                indent_size: parseInt($('fmtIndent').value, 10) || 4,
                use_tabs: false,
                brace_style: $('fmtBrace').value,
                space_around_operators: true,
                align_trailing_comments: $('fmtAlign').checked,
                max_blank_lines: 1,
                keep_blank_lines: $('fmtBlank').checked
            }
        });
    }

    async function formatCode() {
        const code = requireCode('格式化');
        if (code === null) return;
        try {
            const result = await requestFormat(code);
            if (result.code !== undefined) {
                const cursor = cm.getCursor();
                cm.setValue(result.code);
                const line = Math.min(cursor.line, cm.lineCount() - 1);
                cm.setCursor({ line: line, ch: cursor.ch });
                cm.focus();
                toast(result.changed ? '代码已格式化' : '代码格式无需调整', 'ok');
            }
        } catch (err) {
            toast('格式化失败：' + err.message, 'err');
        }
    }

    /* -------------------------- 格式化对比视图 -------------------------- */
    let fmtOriginalText = '';
    let fmtResultText = '';

    function openFormatView() {
        if (!cm) { toast('先新建或打开一个文件再格式化', 'warn'); return; }
        fmtOriginalText = cm.getValue();
        fmtResultText = '';
        $('formatModal').hidden = false;
        $('fmtOriginal').value = fmtOriginalText;
        $('fmtResult').value = '';
        runFormatPreview();
    }

    function closeFormatView() {
        $('formatModal').hidden = true;
        cm.refresh();
    }

    async function runFormatPreview() {
        const status = $('fmtStatus');
        status.textContent = '格式化中…';
        try {
            const result = await requestFormat(fmtOriginalText);
            fmtResultText = result.code === undefined ? '' : result.code;
            $('fmtOriginal').value = fmtOriginalText;
            $('fmtResult').value = fmtResultText;
            const lines = fmtResultText ? fmtResultText.split('\n').length : 0;
            status.textContent = result.changed
                ? '已重新排版 · 共 ' + lines + ' 行'
                : '当前代码已符合所选格式，无需调整';
        } catch (err) {
            status.textContent = '格式化失败：' + err.message;
        }
    }

    function applyFormatResult() {
        if (!fmtResultText) {
            toast('还没有格式化结果', 'warn');
            return;
        }
        const cursor = cm.getCursor();
        cm.setValue(fmtResultText);
        cm.setCursor({ line: Math.min(cursor.line, cm.lineCount() - 1), ch: cursor.ch });
        cm.focus();
        toast('已把格式化结果应用到编辑器', 'ok');
    }

    /* ------------------------------------------------------------------ */
    /*  模式切换：样例调试 / 批量评测                                        */
    /* ------------------------------------------------------------------ */
    const MODE_KEY = 'cpide.mode';

    function switchMode(mode) {
        const target = mode === 'judge' ? 'judge' : 'sample';
        document.querySelectorAll('.mode-btn').forEach((btn) => {
            const on = btn.dataset.mode === target;
            btn.classList.toggle('active', on);
            btn.setAttribute('aria-selected', on ? 'true' : 'false');
        });
        document.querySelectorAll('.mode-page').forEach((page) => {
            page.classList.toggle('active', page.dataset.modePage === target);
        });
        try { localStorage.setItem(MODE_KEY, target); } catch (err) { /* ignore */ }
        refreshEditors();
        scheduleSaveWorkspace();
    }

    /* ------------------------------------------------------------------ */
    /*  工具抽屉：编译环境 / 插入代码 / 查找替换 / 外观                        */
    /* ------------------------------------------------------------------ */
    function openTools(tabName) {
        $('toolsDrawer').hidden = false;
        if (tabName) openTab(tabName);
    }

    function closeTools() {
        $('toolsDrawer').hidden = true;
    }

    function toggleTools() {
        $('toolsDrawer').hidden = !$('toolsDrawer').hidden;
    }

    /* ------------------------------------------------------------------ */
    /*  标签页                                                              */
    /* ------------------------------------------------------------------ */
    function initTabs() {
        document.querySelectorAll('.tab').forEach((tab) => {
            tab.addEventListener('click', () => {
                document.querySelectorAll('.tab').forEach((t) => t.classList.remove('active'));
                document.querySelectorAll('.tab-page').forEach((p) => p.classList.remove('active'));
                tab.classList.add('active');
                const page = document.querySelector('.tab-page[data-page="' + tab.dataset.tab + '"]');
                if (page) page.classList.add('active');
                if (tab.dataset.tab === 'insert' && !state.snippets.length) loadSnippets();
                if (tab.dataset.tab === 'keys') renderShortcutPanel();
            });
        });
    }

    function openTab(name) {
        const tab = document.querySelector('.tab[data-tab="' + name + '"]');
        if (tab) tab.click();
        $('toolsDrawer').hidden = false;
    }

    /* ------------------------------------------------------------------ */
    /*  编译信息区：折叠 / 完全隐藏                                          */
    /* ------------------------------------------------------------------ */
    const STATUS_HIDDEN_KEY = 'cpide.statusHidden';
    const STATUS_COLLAPSED_KEY = 'cpide.statusCollapsed';

    function setStatusHidden(hidden, persist) {
        document.body.classList.toggle('status-hidden', !!hidden);
        $('btnShowStatus').hidden = !hidden;
        if (persist !== false) {
            try {
                localStorage.setItem(STATUS_HIDDEN_KEY, hidden ? '1' : '0');
            } catch (err) { /* ignore */ }
        }
        const box = $('optStatusHidden');
        if (box) box.checked = !!hidden;
        refreshEditors();
        scheduleSaveWorkspace();
    }

    function isStatusHidden() {
        return document.body.classList.contains('status-hidden');
    }

    /* 折叠 / 展开编译信息正文 */
    function setStatusCollapsed(collapsed, persist) {
        const bar = $('statusbar');
        bar.classList.toggle('collapsed', !!collapsed);
        $('btnToggleStatus').textContent = collapsed ? '▴' : '▾';
        if (persist !== false) {
            try {
                localStorage.setItem(STATUS_COLLAPSED_KEY, collapsed ? '1' : '0');
            } catch (err) { /* ignore */ }
        }
        const box = $('optStatusCollapsed');
        if (box) box.checked = !!collapsed;
        refreshEditors();
        scheduleSaveWorkspace();
    }

    /* 编译信息被隐藏时，用恢复按钮的呼吸效果提示有新结果 */
    function flashRestoreButton() {
        if (!isStatusHidden()) return;
        const restore = $('btnShowStatus');
        restore.classList.remove('attention');
        void restore.offsetWidth;
        restore.classList.add('attention');
        setTimeout(() => restore.classList.remove('attention'), 5000);
    }

    /* ------------------------------------------------------------------ */
    /*  底部面板拖拽                                                        */
    /* ------------------------------------------------------------------ */
    function initResize() {
        const handle = $('resizeHandle');
        let dragging = false;
        let startY = 0;
        let startHeight = 0;

        const onMove = (event) => {
            if (!dragging) return;
            const delta = startY - event.clientY;
            const height = Math.max(90, Math.min(window.innerHeight - 220, startHeight + delta));
            document.body.style.setProperty('--status-height', height + 'px');
        };
        const onUp = () => {
            dragging = false;
            document.removeEventListener('mousemove', onMove);
            document.removeEventListener('mouseup', onUp);
        };
        handle.addEventListener('mousedown', (event) => {
            dragging = true;
            startY = event.clientY;
            startHeight = $('statusbar').getBoundingClientRect().height;
            document.addEventListener('mousemove', onMove);
            document.addEventListener('mouseup', onUp);
            event.preventDefault();
        });
    }

    /* ------------------------------------------------------------------ */
    /*  事件绑定                                                            */
    /* ------------------------------------------------------------------ */
    function bindEvents() {
        $('btnTheme').addEventListener('click', toggleTheme);
        $('btnCompile').addEventListener('click', compileCode);
        $('btnCompileRun').addEventListener('click', compileAndRun);
        $('btnRun').addEventListener('click', () => {
            switchMode('sample');
            runSample();
        });
        $('btnJudge').addEventListener('click', () => {
            switchMode('judge');
            judgeAll();
        });
        $('btnFormat').addEventListener('click', openFormatView);
        $('btnInsert').addEventListener('click', () => openTools('insert'));
        $('btnTools').addEventListener('click', toggleTools);
        $('btnToolsClose').addEventListener('click', closeTools);

        /* ---------------- 标签页 / 分栏 ---------------- */
        $('btnNewTab').addEventListener('click', newTab);
        $('btnSampleCode').addEventListener('click', loadSampleCode);
        $('btnOpenFile').addEventListener('click', () => $('openFileInput').click());
        $('btnDemoDocs').addEventListener('click', toggleDocMenu);
        /* 空状态里的三个入口 */
        $('btnEmptyNew').addEventListener('click', newTab);
        $('btnEmptyOpen').addEventListener('click', () => $('openFileInput').click());
        $('btnEmptyDemo').addEventListener('click', toggleDocMenu);
        $('docMenuList').addEventListener('click', (event) => {
            const item = event.target.closest ? event.target.closest('.doc-menu-item') : null;
            if (!item) return;
            $('docMenu').hidden = true;
            openDemoDoc(item.dataset.doc);
        });
        document.addEventListener('click', (event) => {
            const menu = $('docMenu');
            if (menu.hidden) return;
            if (menu.contains(event.target) || $('btnDemoDocs').contains(event.target)) return;
            menu.hidden = true;
        });
        $('openFileInput').addEventListener('change', (event) => {
            const file = event.target.files && event.target.files[0];
            event.target.value = '';
            if (file) openLocalFile(file);
        });
        $('btnToggleView').addEventListener('click', toggleViewMode);
        $('optPythonPath').addEventListener('change', (event) => {
            state.pythonPath = event.target.value.trim();
            try { localStorage.setItem('cpide.pythonPath', state.pythonPath); } catch (err) { /* ignore */ }
            scheduleSaveWorkspace();
        });
        $('btnSplit').addEventListener('click', () => toggleSplit());
        $('btnToggleSide').addEventListener('click', toggleSide);
        $('btnFoldSide').addEventListener('click', () => setSideHidden(true));
        $('btnCloseSplit').addEventListener('click', () => toggleSplit(false));
        $('btnSwap').addEventListener('click', swapActiveAndCompare);
        $('cmpSelect').addEventListener('change', (event) => setCompareTab(event.target.value));
        $('chkSyncScroll').addEventListener('change', (event) => {
            state.syncScroll = event.target.checked;
        });
        $('confirmYes').addEventListener('click', () => closeConfirm(true));
        $('confirmNo').addEventListener('click', () => closeConfirm(false));
        $('fileName').addEventListener('change', () => {
            const tab = getActiveTab();
            if (tab) renameTab(tab.id, $('fileName').value);
        });
        $('fileName').addEventListener('keydown', (event) => {
            if (event.key === 'Enter') {
                event.preventDefault();
                $('fileName').blur();
            }
        });

        /* ---------------- 自定义 checker ---------------- */
        $('btnCheckerTemplate').addEventListener('click', insertCheckerTemplate);
        $('btnDemoChecker').addEventListener('click', loadDemoCheckerArchive);
        $('btnTestlibView').addEventListener('click', viewTestlib);
        $('btnTestlibDownload').addEventListener('click', downloadTestlib);
        $('optChecker').addEventListener('change', updateCheckerHint);
        $('btnSearchMini').addEventListener('click', () => {
            openTools('search');
            $('searchFind').focus();
            $('searchFind').select();
        });

        // 格式化对比视图
        $('btnFmtRun').addEventListener('click', runFormatPreview);
        $('btnFmtApply').addEventListener('click', applyFormatResult);
        $('btnFmtQuick').addEventListener('click', async () => {
            await formatCode();
            fmtOriginalText = cm.getValue();
            $('fmtOriginal').value = fmtOriginalText;
            await runFormatPreview();
        });
        $('btnFmtClose').addEventListener('click', closeFormatView);
        $('formatModal').addEventListener('click', (event) => {
            if (event.target === $('formatModal')) closeFormatView();
        });

        // 模式切换
        document.querySelectorAll('.mode-btn').forEach((btn) => {
            btn.addEventListener('click', () => switchMode(btn.dataset.mode));
        });

        $('btnSampleRun').addEventListener('click', runSample);
        $('btnSampleAdd').addEventListener('click', addSample);
        $('btnSampleDel').addEventListener('click', deleteSample);
        $('btnSampleReload').addEventListener('click', loadSamples);
        $('sampleInput').addEventListener('input', persistSampleEdits);
        $('sampleExpected').addEventListener('input', persistSampleEdits);
        $('btnClearOutput').addEventListener('click', () => {
            $('sampleOutput').value = '';
            $('sampleStderr').value = '';
            $('stderrBox').hidden = true;
            const sample = state.samples[state.activeSample];
            if (sample) {
                sample.output = '';
                sample.stderr = '';
            }
        });

        // 文件上传：文件选择框铺满上传区，点击上传区即触发它
        const dropzone = $('dropzone');
        const fileInput = $('fileInput');
        fileInput.addEventListener('change', () => {
            addFiles(fileInput.files);
            fileInput.value = '';
        });
        ['dragenter', 'dragover'].forEach((name) => dropzone.addEventListener(name, (event) => {
            event.preventDefault();
            dropzone.classList.add('drag');
        }));
        ['dragleave', 'drop'].forEach((name) => dropzone.addEventListener(name, (event) => {
            event.preventDefault();
            dropzone.classList.remove('drag');
        }));
        dropzone.addEventListener('drop', (event) => {
            if (event.dataTransfer && event.dataTransfer.files) addFiles(event.dataTransfer.files);
        });
        $('btnLoadDemo').addEventListener('click', loadDemoTests);

        // 编译环境
        ['optStd', 'optLevel', 'optDebug', 'optStatic', 'optSanitize', 'optExtra']
            .forEach((id) => {
                const el = $(id);
                el.addEventListener('change', () => {
                    updateCommandPreview();
                    scheduleSaveWorkspace();
                });
                el.addEventListener('input', updateCommandPreview);
            });
        document.querySelectorAll('input[data-flag="warning"]').forEach((el) => {
            el.addEventListener('change', () => {
                updateCommandPreview();
                scheduleSaveWorkspace();
            });
        });

        // 代码片段
        $('btnNewSnippet').addEventListener('click', newSnippet);
        $('btnSnippetSave').addEventListener('click', saveSnippet);
        $('btnSnippetCancel').addEventListener('click', () => {
            $('snippetEditorBox').hidden = true;
            state.editingSnippetId = null;
        });

        // 查找替换
        $('btnFindNext').addEventListener('click', () => findNext(1));
        $('btnFindPrev').addEventListener('click', () => findNext(-1));
        $('btnFindAll').addEventListener('click', findAll);
        $('btnReplaceAll').addEventListener('click', replaceAll);
        $('btnReplaceOne').addEventListener('click', replaceCurrent);
        $('btnReplaceSel').addEventListener('click', replaceInSelection);
        $('searchFind').addEventListener('keydown', (event) => {
            if (event.key === 'Enter') {
                event.preventDefault();
                findNext(event.shiftKey ? -1 : 1);
            }
        });
        $('searchFind').addEventListener('input', () => {
            const count = countMatches();
            $('searchStatus').textContent = count ? ('共 ' + count + ' 处匹配') : '';
        });

        // 编译信息面板
        $('btnClearLog').addEventListener('click', () => {
            $('compileLog').innerHTML = '<p class="empty-hint">编译信息已清空。</p>';
        });
        $('btnToggleStatus').addEventListener('click', () => {
            setStatusCollapsed(!$('statusbar').classList.contains('collapsed'), true);
        });
        // 完全隐藏 / 恢复编译信息区
        $('btnHideStatus').addEventListener('click', () => {
            setStatusHidden(true, true);
            toast('编译信息已隐藏，点击编辑器右下角「编译面板」可恢复', 'ok');
        });
        $('btnShowStatus').addEventListener('click', () => {
            setStatusHidden(false, true);
        });

        // 外观：字体 / 字号 / 主题 / 编译信息区
        document.querySelectorAll('#fontPicker .option-card').forEach((card) => {
            card.addEventListener('click', () => applyMonoFont(card.dataset.mono, true));
        });
        document.querySelectorAll('#fontSizePicker .option-chip').forEach((chip) => {
            chip.addEventListener('click', () => applyEditorFontSize(chip.dataset.size, true));
        });
        document.querySelectorAll('#themePicker .option-chip').forEach((chip) => {
            chip.addEventListener('click', () => applyTheme(chip.dataset.theme));
        });
        $('optStatusHidden').addEventListener('change', (event) => {
            setStatusHidden(event.target.checked, true);
        });
        $('optStatusCollapsed').addEventListener('change', (event) => {
            setStatusCollapsed(event.target.checked, true);
        });

        // Markdown 代码块：高亮 / 行号
        $('optMdHighlight').addEventListener('change', (event) => {
            state.mdOptions.highlight = !!event.target.checked;
            refreshDocPreviews();
            scheduleSaveWorkspace();
        });
        $('optMdLineNumbers').addEventListener('change', (event) => {
            state.mdOptions.lineNumbers = !!event.target.checked;
            refreshDocPreviews();
            scheduleSaveWorkspace();
        });

        // 导出到电脑
        $('btnExport').addEventListener('click', exportCurrentFile);
        $('btnExportCurrent').addEventListener('click', exportCurrentFile);
        $('btnExportAll').addEventListener('click', exportAllFiles);
        $('btnReloadWorkspace').addEventListener('click', reloadWorkspace);

        // 快捷键设置面板
        $('btnKeysResetAll').addEventListener('click', resetAllShortcuts);
        $('keysFilter').addEventListener('input', renderShortcutPanel);

        // 配置说明弹窗
        $('btnConfigHelp').addEventListener('click', () => { $('configModal').hidden = false; });
        $('btnConfigClose').addEventListener('click', () => { $('configModal').hidden = true; });
        $('configModal').addEventListener('click', (event) => {
            if (event.target === $('configModal')) $('configModal').hidden = true;
        });

        // 快捷键：先处理「正在录制」，再按注册表分发
        document.addEventListener('keydown', (event) => {
            if (state.recording) {
                event.preventDefault();
                event.stopPropagation();
                handleRecordingKey(event);
                return;
            }
            const chord = canonFromEvent(event);
            if (!chord) return;
            const def = globalChordMap.get(chord);
            if (!def) return;
            event.preventDefault();
            def.run(event);
        });
    }

    /* 录制快捷键：Esc 取消，Backspace 删除该快捷键，其余按下即绑定 */
    function handleRecordingKey(event) {
        const id = state.recording;
        if (!id) return;
        if (event.key === 'Escape') {
            stopRecording();
            toast('已取消录制', '');
            return;
        }
        if (event.key === 'Backspace' && !event.ctrlKey && !event.altKey && !event.shiftKey) {
            delete state.shortcuts[id];
            persistShortcuts();
            rebuildGlobalChordMap();
            applyEditorShortcuts();
            stopRecording();
            toast('已删除该快捷键', '');
            return;
        }
        /* 只按下修饰键时先等着 */
        if (['Control', 'Alt', 'Shift', 'Meta', 'OS'].indexOf(event.key) >= 0) return;
        const chord = canonFromEvent(event);
        if (!chord) return;
        setShortcut(id, chord);
        stopRecording();
    }

    /* ------------------------------------------------------------------ */
    /*  启动                                                                */
    /* ------------------------------------------------------------------ */
    async function init() {
        let theme = 'dark';
        try {
            theme = localStorage.getItem(THEME_KEY) || (window.matchMedia &&
                window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark');
        } catch (err) { /* ignore */ }
        applyTheme(theme);

        // 先恢复外观设置，再初始化编辑器，保证 CodeMirror 一开始就是目标字体
        let mono = 'default';
        let fontSize = '13.5';
        try {
            mono = localStorage.getItem(MONO_KEY) || 'default';
            fontSize = localStorage.getItem(FONT_SIZE_KEY) || '13.5';
        } catch (err) { /* ignore */ }
        applyMonoFont(mono, false);
        applyEditorFontSize(fontSize, false);

        initTabs();
        initResize();
        initSplitResize();
        bindEvents();
        updateCommandPreview();
        loadSamples();
        loadSnippets();

        // 恢复上次「完全隐藏 / 折叠编译信息」的偏好
        try {
            if (localStorage.getItem(STATUS_HIDDEN_KEY) === '1') {
                setStatusHidden(true, false);
            }
            // 默认折叠成一条细条（首次使用没有偏好记录时）
            const collapsed = localStorage.getItem(STATUS_COLLAPSED_KEY);
            setStatusCollapsed(collapsed === null ? true : collapsed === '1', false);
        } catch (err) { /* ignore */ }

        // 恢复上次所在模式
        try {
            switchMode(localStorage.getItem(MODE_KEY) || 'sample');
        } catch (err) {
            switchMode('sample');
        }

        // 快捷键：先读浏览器缓存，工作区里有记录则以工作区为准
        loadShortcuts();
        renderShortcutPanel();

        // 读回上次的工作区（代码 / 编译信息 / 字体字号 / 各种开关）
        const workspace = await loadWorkspace();
        applyWorkspaceSettings(workspace ? workspace.settings : null);

        try {
            state.pythonPath = localStorage.getItem('cpide.pythonPath') || '';
        } catch (err) { /* ignore */ }
        const pythonInput = $('optPythonPath');
        if (pythonInput) pythonInput.value = state.pythonPath;

        // 恢复上次打开的标签页（没有记录就新建一个 main.cpp）
        restoreTabs(workspace);
        showActiveEditor();
        renderTabs();
        renderCompareSelect();
        if (state.split) {
            toggleSplit(true);
        }
        updateHeaderFileName();
        updateCheckerHint();
        loadTestlibInfo();
        loadLanguages();
        loadAboutInfo();

        // 恢复上一次的编译信息
        if (workspace && workspace.compile) {
            state.lastCompile = workspace.compile;
            updateCompileHeader(workspace.compile);
            renderCompileLog(workspace.compile);
        }

        // 工作区恢复完毕，之后才允许往回写
        workspaceReady = true;

        // 关闭窗口前把最后的状态落到磁盘上
        window.addEventListener('beforeunload', () => {
            try {
                const data = collectWorkspace();
                localStorage.setItem(WORKSPACE_KEY, JSON.stringify(data));
                if (navigator.sendBeacon) {
                    navigator.sendBeacon('/api/workspace',
                        new Blob([JSON.stringify({ workspace: data })],
                            { type: 'application/json' }));
                }
            } catch (err) { /* ignore */ }
        });

        // ?demo=1 —— 直接预载入内置示例测试集，方便快速体验评测流程
        try {
            if (new URLSearchParams(location.search).has('demo')) {
                loadDemoTests();
            }
        } catch (err) { /* ignore */ }

        api('/api/toolchain').then((info) => {
            if (!info.ok) {
                toast('未检测到 C++ 编译器，请确认 winlibs 已解压', 'err');
            } else {
                const first = (info.version || '').split('\n')[0];
                console.log('[CP-IDE] ' + first);
            }
        }).catch(() => { /* ignore */ });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
