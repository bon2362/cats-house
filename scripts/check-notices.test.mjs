import assert from 'node:assert/strict'
import { execFile } from 'node:child_process'
import test from 'node:test'
import { promisify } from 'node:util'

const execFileAsync = promisify(execFile)

async function runNoticeCheck(targetPath) {
  try {
    await execFileAsync('node', ['scripts/check-notices.mjs', targetPath])
  } catch (error) {
    throw new Error(`${error.stderr}\n${error.stdout}`)
  }
}

test('rejects a Gramps-derived file missing from NOTICE', async () => {
  await assert.rejects(
    runNoticeCheck('scripts/test-fixtures/missing-notice.js'),
    /NOTICE/
  )
})

test('accepts documentation that only mentions the marker name', async () => {
  await runNoticeCheck('scripts/test-fixtures/marker-documentation.md')
})
