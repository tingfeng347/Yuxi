export const CHUNK_PRESET_OPTIONS = [
  {
    value: 'general',
    label: 'General',
    description: '通用分块：按分隔符和长度切分，适合大多数普通文档。'
  },
  {
    value: 'qa',
    label: 'QA',
    description: '问答分块：优先抽取问题-回答结构，适合 FAQ、题库、问答手册。'
  },
  {
    value: 'book',
    label: 'Book',
    description: '书籍分块：强化章节标题识别并做层级合并，适合教材、手册、长章节文档。'
  },
  {
    value: 'laws',
    label: 'Laws',
    description: '法规分块：按法条层级组织与合并，适合法律法规、制度规范类文本。'
  },
  {
    value: 'semantic',
    label: 'Semantic',
    description: '语义分块：利用嵌入和聚类算法进行语义切分，并自动增强标题上下文。'
  },
  {
    value: 'separator',
    label: 'Separator',
    description: '严格分隔：命中分隔符即切分，仅超长片段内部继续按长度切分。'
  }
]

export const CHUNK_PRESET_LABEL_MAP = Object.fromEntries(
  CHUNK_PRESET_OPTIONS.map((item) => [item.value, item.label])
)

export const CHUNK_PRESET_DESCRIPTION_MAP = Object.fromEntries(
  CHUNK_PRESET_OPTIONS.map((item) => [item.value, item.description])
)

export const getChunkPresetDescription = (presetId) =>
  CHUNK_PRESET_DESCRIPTION_MAP[presetId] || CHUNK_PRESET_DESCRIPTION_MAP.general

export const isPlainObject = (value) =>
  value !== null && typeof value === 'object' && !Array.isArray(value)

export const buildChunkParserConfigPayload = (source, { includeSizeOverlap = true } = {}) => {
  if (!isPlainObject(source)) {
    return {}
  }

  const config = {}
  if (includeSizeOverlap) {
    if (source.chunk_token_num !== undefined && source.chunk_token_num !== null) {
      config.chunk_token_num = source.chunk_token_num
    }
    if (source.overlapped_percent !== undefined && source.overlapped_percent !== null) {
      config.overlapped_percent = source.overlapped_percent
    }
  }
  if (source.delimiter) {
    config.delimiter = source.delimiter
  }

  return config
}

export const buildChunkParamsPayload = (source, options = {}) => {
  if (!isPlainObject(source)) {
    return {}
  }

  const payload = {}
  const chunkParserConfig = buildChunkParserConfigPayload(source.chunk_parser_config, options)
  if (Object.keys(chunkParserConfig).length > 0) {
    payload.chunk_parser_config = chunkParserConfig
  }
  if (source.chunk_preset_id) {
    payload.chunk_preset_id = source.chunk_preset_id
  }

  return payload
}
