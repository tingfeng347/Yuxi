const DICEBEAR_GLYPHS_AVATAR_BASE_URL = 'https://api.dicebear.com/10.x/glyphs/svg'

const normalizeSeed = (id) => {
  if (id === null || id === undefined || String(id).trim() === '') {
    throw new Error('generatePixelAvatar requires an id')
  }
  return String(id).trim()
}

export const generatePixelAvatar = (id) => {
  const seed = normalizeSeed(id)
  return `${DICEBEAR_GLYPHS_AVATAR_BASE_URL}?seed=${encodeURIComponent(seed)}`
}
