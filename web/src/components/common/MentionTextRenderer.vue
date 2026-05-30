<template>
  <span class="mention-text-renderer">
    <template v-for="segment in segments" :key="`${segment.kind}-${segment.start}-${segment.end}`">
      <span v-if="segment.kind === 'text'" class="mention-text-segment">{{ segment.text }}</span>
      <span
        v-else
        class="mention-ref-token"
        :class="[`mention-ref-${segment.type}`, { 'mention-ref-editable': editable }]"
        :contenteditable="editable ? 'false' : undefined"
        :data-mention-raw="editable ? segment.raw : undefined"
        :data-mention-type="editable ? segment.type : undefined"
        :data-mention-value="editable ? segment.value : undefined"
        :title="segment.raw"
      >
        <component
          :is="getTokenIcon(segment)"
          class="mention-ref-icon"
          :style="getIconStyle(segment)"
          :stroke-width="2.2"
          :size="15"
        />
        <span class="mention-ref-label">{{ getTokenLabel(segment) }}</span>
      </span>
    </template>
  </span>
</template>

<script setup>
import { computed } from 'vue'
import { FolderFilled } from '@ant-design/icons-vue'
import { BookMarked, BookOpen, Bot, Plug } from 'lucide-vue-next'
import { getFileIcon, getFileIconColor } from '@/utils/file_utils'
import { getMentionDisplayLabel, parseMentionText } from '@/utils/mention_utils'

const props = defineProps({
  content: {
    type: String,
    default: ''
  },
  editable: {
    type: Boolean,
    default: false
  },
  displayLabels: {
    type: Object,
    default: () => ({})
  }
})

const segments = computed(() => parseMentionText(props.content))

const typeIcons = {
  knowledge: BookOpen,
  skill: BookMarked,
  mcp: Plug,
  subagent: Bot
}

const getTokenIcon = (segment) => {
  if (segment.type === 'file') {
    return segment.value.endsWith('/') ? FolderFilled : getFileIcon(segment.value)
  }
  return typeIcons[segment.type] || Plug
}

const getIconStyle = (segment) => {
  if (segment.type === 'file') {
    return {
      color: segment.value.endsWith('/') ? '#ffa940' : getFileIconColor(segment.value)
    }
  }
  return null
}

const getTokenLabel = (segment) =>
  getMentionDisplayLabel(segment.type, segment.value, props.displayLabels)
</script>

<style lang="less" scoped>
.mention-text-renderer {
  white-space: inherit;
}

.mention-text-segment {
  white-space: inherit;
}

.mention-ref-token {
  display: inline-flex;
  align-items: baseline;
  gap: 2px;
  max-width: 100%;
  color: var(--main-700);
  line-height: normal;
  vertical-align: baseline;
  white-space: nowrap;
}

.mention-ref-editable {
  user-select: all;
}

.mention-ref-icon {
  position: relative;
  top: 2px;
  display: inline-flex;
  align-items: center;
  flex-shrink: 0;
  font-size: 13px;
  line-height: 1;
  margin-left: 4px;
}

.mention-ref-label {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  line-height: normal;
  font-weight: 500;
}
</style>
