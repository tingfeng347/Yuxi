import assert from 'node:assert/strict'

import {
  buildToolApprovalDecisions,
  hasPendingInterruptPayload,
  isToolApprovalMode
} from '../toolApproval.js'

assert.equal(isToolApprovalMode('default'), true)
assert.equal(isToolApprovalMode('always_trust'), true)
assert.equal(isToolApprovalMode('unknown'), false)

assert.deepEqual(buildToolApprovalDecisions({ 0: 'approve', 1: 'reject' }, 2), [
  { type: 'approve' },
  { type: 'reject', message: '用户拒绝执行该操作' }
])
assert.equal(hasPendingInterruptPayload({ kind: 'question', questions: [{}] }), true)
assert.equal(hasPendingInterruptPayload({ kind: 'tool_approval', actionRequests: [{}] }), true)
assert.equal(hasPendingInterruptPayload({ kind: 'tool_approval', actionRequests: [] }), false)

console.log('toolApproval: all assertions passed')
