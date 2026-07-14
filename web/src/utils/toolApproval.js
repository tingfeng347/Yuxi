export const TOOL_APPROVAL_MODES = ['default', 'always_trust']

export const isToolApprovalMode = (value) => TOOL_APPROVAL_MODES.includes(value)

export const buildToolApprovalDecisions = (selectedDecisions, actionCount) =>
  Array.from({ length: actionCount }, (_, index) =>
    selectedDecisions[index] === 'approve'
      ? { type: 'approve' }
      : { type: 'reject', message: '用户拒绝执行该操作' }
  )

export const hasPendingInterruptPayload = (pendingInterrupt) => {
  if (!pendingInterrupt) return false
  if (pendingInterrupt.kind === 'tool_approval') {
    return Array.isArray(pendingInterrupt.actionRequests) && pendingInterrupt.actionRequests.length > 0
  }
  return Array.isArray(pendingInterrupt.questions) && pendingInterrupt.questions.length > 0
}
