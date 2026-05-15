<template>
  <div
    :class="[
      'yk-markdown-preview',
      'flat-md-preview',
      { 'is-dark': themeStore.isDark, 'is-compact': compact }
    ]"
    v-html="renderedMarkdown"
    @click="handleSvgAction"
  ></div>
</template>

<script setup>
import { computed, shallowRef, watch } from 'vue'
import { useThemeStore } from '@/stores/theme'
import { renderMarkdown } from '@/utils/markdown_preview'
import 'katex/dist/katex.min.css'

const props = defineProps({
  content: {
    type: String,
    default: ''
  },
  compact: {
    type: Boolean,
    default: false
  }
})

const themeStore = useThemeStore()
const shikiTheme = computed(() => (themeStore.isDark ? 'github-dark' : 'github-light'))
const renderedMarkdown = shallowRef('')

watch(
  [() => props.content, shikiTheme],
  async ([content, theme], _, onCleanup) => {
    let expired = false
    onCleanup(() => {
      expired = true
    })

    if (!content) {
      renderedMarkdown.value = ''
      return
    }

    const html = await renderMarkdown(content, { theme })
    if (!expired) renderedMarkdown.value = html
  },
  { immediate: true }
)

// === SVG 操作按钮事件委托 ===
const handleSvgAction = async (e) => {
  const btn = e.target.closest('.svg-copy-btn, .svg-png-btn')
  if (!btn) return

  const container = btn.closest('.svg-inline-render')
  const svgEl = container?.querySelector('svg')
  if (!svgEl) return

  if (btn.classList.contains('svg-copy-btn')) {
    await copySvgText(svgEl, btn)
  } else if (btn.classList.contains('svg-png-btn')) {
    await copySvgAsPng(svgEl, btn)
  }
}

// 复制 SVG 源代码
const copySvgText = async (svgEl, btn) => {
  try {
    await navigator.clipboard.writeText(svgEl.outerHTML)
    showCopiedFeedback(btn)
  } catch (err) {
    console.error('复制 SVG 失败:', err)
  }
}

// 复制为 PNG 图片
const copySvgAsPng = async (svgEl, btn) => {
  const svgContent = svgEl.outerHTML
  const blob = new Blob([svgContent], { type: 'image/svg+xml' })
  const url = URL.createObjectURL(blob)

  try {
    // 三级递进尺寸策略：
    // 1) viewBox 固有坐标尺寸（最佳品质，不受 CSS 缩放影响）
    let width, height
    const vb = svgEl.viewBox
    if (vb && vb.baseVal && vb.baseVal.width && vb.baseVal.height) {
      width = vb.baseVal.width
      height = vb.baseVal.height
    }

    // 2) 客户端渲染尺寸（SVG 在 DOM 中一定可获取）
    if (!width || !height) {
      const rect = svgEl.getBoundingClientRect()
      width = rect.width
      height = rect.height
    }

    // 3) 回退
    if (!width || !height) { width = 800; height = 600 }

    const img = await new Promise((resolve, reject) => {
      const image = new Image()
      image.onload = () => resolve(image)
      image.onerror = reject
      image.src = url
    })

    const canvas = document.createElement('canvas')
    canvas.width = width
    canvas.height = height
    const ctx = canvas.getContext('2d')
    // 不填充背景色 — Canvas 默认为全透明
    // 背景色由 SVG 自身决定
    ctx.drawImage(img, 0, 0, width, height)

    const pngBlob = await new Promise(resolve => canvas.toBlob(resolve, 'image/png'))
    if (pngBlob) {
      await navigator.clipboard.write([
        new ClipboardItem({ 'image/png': pngBlob })
      ])
      showCopiedFeedback(btn)
    }
  } catch (err) {
    console.error('复制为 PNG 失败:', err)
    // fallback: 尝试复制 SVG 源码
    try {
      await navigator.clipboard.writeText(svgContent)
      console.log('PNG 复制失败，已回退复制 SVG 源码')
    } catch {}
  } finally {
    URL.revokeObjectURL(url)
  }
}

// 反馈：按钮文字短暂变为「已复制」
const showCopiedFeedback = (btn) => {
  const originalText = btn.textContent
  btn.textContent = '已复制'
  setTimeout(() => {
    btn.textContent = originalText
  }, 1500)
}
</script>

<style lang="less">
.yk-markdown-preview,
.flat-md-preview.yk-markdown-preview {
  max-width: 100%;
  color: var(--gray-1000);
  font-family:
    -apple-system, BlinkMacSystemFont, 'Noto Sans SC', 'PingFang SC', 'Microsoft YaHei',
    'Hiragino Sans GB', 'Source Han Sans CN', sans-serif;
  font-size: 0.95rem;
  line-height: 1.75;
  word-break: break-word;
  padding: 0;

  &.is-compact {
    font-size: 14px;
    line-height: 1.65;
  }

  h1,
  h2 {
    font-size: 1.1rem;
  }

  h3,
  h4 {
    font-size: 1.05rem;
  }

  h5,
  h6 {
    font-size: 1rem;
  }

  strong {
    font-weight: 500;
  }

  p:last-child {
    margin-bottom: 0;
  }

  li > p,
  ol > p,
  ul > p {
    margin: 0.25rem 0;
  }

  ul,
  ol {
    padding-left: 1.625rem;
  }

  ul li::marker,
  ol li::marker {
    color: var(--main-bright);
  }

  .contains-task-list {
    padding-left: 0;
    list-style: none;
  }

  .task-list-item {
    list-style: none;
  }

  .task-list-item-checkbox {
    margin-right: 8px;
    transform: translateY(1px);
  }

  a {
    color: var(--main-700);
  }

  hr {
    height: 1px;
    margin: 1.25rem 0;
    border: 0;
    background: linear-gradient(90deg, transparent, var(--gray-200), transparent);
  }

  blockquote {
    margin: 1rem 0;
    padding: 0.25rem 0 0.25rem 1rem;
    border-left: 3px solid var(--gray-200);
    color: var(--gray-700);
  }

  cite {
    position: relative;
    margin-left: 4px;
    padding: 0 0.25rem;
    border-radius: 4px;
    outline: 2px solid var(--gray-200);
    background-color: var(--gray-200);
    color: var(--gray-800);
    font-size: 12px;
    font-style: normal;
    cursor: pointer;
    user-select: none;

    &:hover::after {
      content: attr(source);
      position: absolute;
      bottom: calc(100% + 6px);
      left: 50%;
      z-index: 1000;
      width: max-content;
      min-width: 100px;
      max-width: 400px;
      padding: 8px 12px;
      border-radius: 6px;
      transform: translateX(-50%);
      background-color: #222;
      color: #fff;
      font-size: 13px;
      line-height: 1.5;
      text-align: center;
      white-space: normal;
      word-break: break-word;
      pointer-events: none;
      box-shadow: 0 2px 8px rgba(0, 0, 0, 0.15);
    }

    &:hover::before {
      content: '';
      position: absolute;
      bottom: 100%;
      left: 50%;
      z-index: 1000;
      transform: translateX(-50%);
      border: 5px solid transparent;
      border-top-color: var(--gray-900);
    }
  }

  code {
    font-family:
      'Menlo', 'Monaco', 'Consolas', 'PingFang SC', 'Noto Sans SC', 'Microsoft YaHei',
      'Hiragino Sans GB', 'Source Han Sans CN', 'Courier New', monospace;
    font-size: 13px;
    line-height: 1.5;
    letter-spacing: 0.025em;
    tab-size: 4;
    -moz-tab-size: 4;
  }

  :not(pre) > code {
    padding: 1px 5px;
    border-radius: 4px;
    background-color: var(--gray-25);
  }

  pre.shiki {
    margin: 12px 0;
    padding: 12px 14px;
    border: 1px solid var(--gray-100);
    border-radius: 8px;
    overflow: auto;
    font-size: 13px;
    line-height: 1.5;
  }

  &:not(.is-dark) pre.shiki {
    background: var(--gray-25) !important;
  }

  &.is-dark pre.shiki {
    border-color: var(--gray-200);
  }

  table {
    width: 100%;
    border-collapse: collapse;
    margin: 2em 0;
    font-size: 15px;
    display: table;
    outline: 1px solid var(--gray-100);
    outline-offset: 12px;
    border-radius: 8px;
  }

  th,
  td {
    padding: 0.5rem 0;
    text-align: left;
    border: none;
  }

  td {
    border-bottom: 1px solid var(--gray-100);
    color: var(--gray-800);
  }

  tbody tr:last-child td {
    border-bottom: none;
  }

  th {
    border-bottom: 1px solid var(--gray-200);
    color: var(--gray-800);
    font-weight: 600;
  }

  tr {
    background-color: var(--gray-0);
  }

  img {
    max-width: 100%;
    height: auto;
  }

  .katex {
    font-size: 1.05em;
  }

  .katex-display {
    margin: 1rem 0;
    overflow-x: auto;
    overflow-y: hidden;
  }

  .frontmatter-card {
    margin: 0 0 20px;
    padding: 12px 14px;
    border-radius: 8px;
    background: var(--gray-25);
  }

  .frontmatter-card .fm-body {
    display: grid;
    gap: 6px;
  }

  .frontmatter-card .fm-row {
    display: grid;
    grid-template-columns: 96px minmax(0, 1fr);
    gap: 14px;
    align-items: baseline;
  }

  .frontmatter-card .fm-key {
    color: var(--gray-500);
    font-family: 'JetBrains Mono', 'Fira Code', 'Monaco', 'Menlo', monospace;
    font-size: 12px;
    line-height: 1.5;
  }

  .frontmatter-card .fm-value {
    color: var(--gray-800);
    font-size: 13px;
    line-height: 1.5;
    min-width: 0;
  }

  .frontmatter-card .fm-doc-title {
    color: var(--gray-1000);
    font-weight: 600;
  }

  .frontmatter-card .fm-tag {
    display: inline-flex;
    align-items: center;
    margin: 0 4px 4px 0;
    padding: 1px 6px;
    border-radius: 4px;
    background: var(--gray-100);
    color: var(--gray-700);
    font-size: 12px;
    line-height: 1.5;
  }

  .frontmatter-card .fm-json {
    margin: 2px 0 0;
    padding: 8px 10px;
    border-radius: 6px;
    overflow: auto;
    background: var(--gray-50);
    color: var(--gray-800);
    font-size: 12px;
    line-height: 1.5;
  }

  .svg-inline-render {
    position: relative;
    max-width: 100%;
    height: auto;
    overflow: auto;
    margin: 12px 0;

    svg {
      max-width: 100%;
      height: auto;
    }

    .svg-actions {
      position: absolute;
      top: 8px;
      right: 8px;
      z-index: 10;
      display: none;
      gap: 4px;

      .svg-action-btn {
        display: inline-flex;
        align-items: center;
        padding: 3px 8px;
        border: 1px solid var(--gray-200);
        border-radius: 4px;
        background: var(--gray-0);
        color: var(--gray-700);
        font-size: 12px;
        line-height: 1.5;
        cursor: pointer;
        transition: all 0.15s ease;
        white-space: nowrap;
        user-select: none;

        &:hover {
          background: var(--gray-100);
          color: var(--gray-900);
        }
      }
    }

    &:hover .svg-actions {
      display: inline-flex;
    }
  }

  &.is-dark .svg-inline-render {
    background: rgba(255, 255, 255, 0.03);
    border-radius: 4px;
  }

  &.is-dark .svg-actions .svg-action-btn {
    background: rgba(255, 255, 255, 0.08);
    border-color: rgba(255, 255, 255, 0.12);
    color: var(--gray-300);

    &:hover {
      background: rgba(255, 255, 255, 0.15);
      color: var(--gray-100);
    }
  }
}
</style>
