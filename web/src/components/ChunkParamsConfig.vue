<template>
  <div class="chunk-params-config">
    <div class="params-info">
      <p>调整分块参数可以控制文本的切分方式，影响检索质量和文档加载效率。</p>
    </div>
    <a-form :model="localParams" name="chunkConfig" autocomplete="off" layout="vertical">
      <a-form-item v-if="showPreset" name="chunk_preset_id">
        <template #label>
          <span class="chunk-preset-label">
            分块策略
            <a-tooltip :title="presetDescription">
              <QuestionCircleOutlined class="chunk-preset-help-icon" />
            </a-tooltip>
          </span>
        </template>
        <a-select
          v-model:value="localParams.chunk_preset_id"
          :options="presetOptions"
          style="width: 100%"
        />
        <p class="param-description">
          预设策略对齐 RAGFlow：General、QA、Book、Laws。
          <span v-if="allowPresetFollowDefault">留空时沿用知识库默认策略。</span>
        </p>
      </a-form-item>

      <div class="chunk-row">
        <a-form-item v-if="showChunkSizeOverlap" name="chunk_token_num">
          <template #label>
            <span class="chunk-preset-label">
              最大 Token 数
              <a-tooltip title="每个文本片段的最大 token 数，留空时使用默认值 512">
                <QuestionCircleOutlined class="chunk-preset-help-icon" />
              </a-tooltip>
            </span>
          </template>
          <a-input-number
            v-model:value="parserConfig.chunk_token_num"
            :min="100"
            :max="10000"
            placeholder="默认 512"
            style="width: 100%"
          />
        </a-form-item>
        <a-form-item v-if="showChunkSizeOverlap" name="overlapped_percent">
          <template #label>
            <span class="chunk-preset-label">
              重叠比例 (%)
              <a-tooltip title="相邻文本片段按 token 数计算的重叠比例，留空时使用默认值 0">
                <QuestionCircleOutlined class="chunk-preset-help-icon" />
              </a-tooltip>
            </span>
          </template>
          <a-input-number
            v-model:value="parserConfig.overlapped_percent"
            :min="0"
            :max="99"
            placeholder="默认 0"
            style="width: 100%"
          />
        </a-form-item>
        <a-form-item v-if="showQaSplit" name="delimiter">
          <template #label>
            <span class="chunk-preset-label">
              分隔符
              <a-tooltip title="支持 \\n、\\t 等转义字符。留空时使用默认分隔符 \\n">
                <QuestionCircleOutlined class="chunk-preset-help-icon" />
              </a-tooltip>
            </span>
          </template>
          <a-input
            v-model:value="parserConfig.delimiter"
            placeholder="默认 \\n，可输入 \\n\\n\\n 或 ---"
            style="width: 100%"
          />
        </a-form-item>
      </div>
    </a-form>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { QuestionCircleOutlined } from '@ant-design/icons-vue'
import {
  CHUNK_PRESET_OPTIONS,
  CHUNK_PRESET_LABEL_MAP,
  getChunkPresetDescription,
  isPlainObject
} from '@/utils/chunk_presets'

const props = defineProps({
  tempChunkParams: {
    type: Object,
    required: true
  },
  showQaSplit: {
    type: Boolean,
    default: true
  },
  showChunkSizeOverlap: {
    type: Boolean,
    default: true
  },
  showPreset: {
    type: Boolean,
    default: true
  },
  allowPresetFollowDefault: {
    type: Boolean,
    default: false
  },
  databasePresetId: {
    type: String,
    default: 'general'
  }
})

const localParams = computed(() => props.tempChunkParams)
const fallbackParserConfig = ref({})

const parserConfig = computed(() => {
  if (!isPlainObject(props.tempChunkParams.chunk_parser_config)) {
    return fallbackParserConfig.value
  }
  return props.tempChunkParams.chunk_parser_config
})

const presetOptions = computed(() => {
  const options = []
  const defaultPresetLabel = CHUNK_PRESET_LABEL_MAP[props.databasePresetId] || 'General'

  if (props.allowPresetFollowDefault) {
    options.push({
      value: '',
      label: `沿用知识库默认（${defaultPresetLabel}）`
    })
  }

  options.push(...CHUNK_PRESET_OPTIONS.map(({ value, label }) => ({ value, label })))

  return options
})

const effectivePresetId = computed(
  () => props.tempChunkParams.chunk_preset_id || props.databasePresetId || 'general'
)
const presetDescription = computed(() => getChunkPresetDescription(effectivePresetId.value))
</script>

<style scoped>
.chunk-params-config {
  width: 100%;
}

.params-info {
  margin-bottom: 16px;
}

.params-info p {
  margin: 0;
  color: var(--gray-500);
  font-size: 14px;
  line-height: 1.5;
}

.chunk-row {
  display: flex;
  gap: 16px;
  margin-bottom: 8px;
}

.chunk-row > .ant-form-item {
  flex: 1;
  margin-bottom: 0;
}


.param-description {
  font-size: 12px;
  color: var(--gray-400);
  margin: 4px 0 0 0;
  line-height: 1.4;
}

.chunk-preset-label {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.chunk-preset-help-icon {
  color: var(--gray-500);
  cursor: help;
  font-size: 14px;
}
</style>
