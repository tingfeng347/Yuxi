import assert from 'node:assert/strict'
import { generatePixelAvatar } from '../pixelAvatar.js'

const DICEBEAR_GLYPHS_AVATAR_BASE_URL = 'https://api.dicebear.com/10.x/glyphs/svg'

const run = () => {
  {
    const first = generatePixelAvatar('user-001')
    const second = generatePixelAvatar('user-001')
    assert.equal(first, second, 'Same ID should generate the same avatar')
    console.log('T1 Stable output: PASS')
  }

  {
    const first = generatePixelAvatar('user-001')
    const second = generatePixelAvatar('user-002')
    assert.notEqual(first, second, 'Different IDs should generate different avatars')
    console.log('T2 Different IDs: PASS')
  }

  {
    const avatar = generatePixelAvatar('user-003')
    assert.equal(
      avatar,
      `${DICEBEAR_GLYPHS_AVATAR_BASE_URL}?seed=user-003`,
      'Should return a DiceBear glyphs avatar URL'
    )
    console.log('T3 DiceBear URL: PASS')
  }

  {
    const avatar = generatePixelAvatar(' user/中文 ')
    assert.equal(
      avatar,
      `${DICEBEAR_GLYPHS_AVATAR_BASE_URL}?seed=user%2F%E4%B8%AD%E6%96%87`,
      'Seed should be trimmed and URL encoded'
    )
    console.log('T4 Encoded seed: PASS')
  }

  {
    assert.throws(
      () => generatePixelAvatar(''),
      /requires an id/,
      'Empty ID should be treated as invalid data'
    )
    assert.throws(
      () => generatePixelAvatar(null),
      /requires an id/,
      'Null ID should be treated as invalid data'
    )
    console.log('T5 Missing ID fails: PASS')
  }

  console.log('\nAll 5 pixel avatar tests passed!')
}

run()
