import { existsSync, readFileSync, statSync } from 'node:fs'
import { readdir } from 'node:fs/promises'
import { relative, resolve } from 'node:path'

const noticePath = resolve('NOTICE')
const grampsDerivedMarker = /^\s*(?:\/\/|#|\/\*|\*)\s*Gramps-derived:\s*(?:\*\/)?\s*$/m

function getNoticePaths() {
  if (!existsSync(noticePath)) {
    throw new Error('Файл NOTICE не найден.')
  }

  return new Set(
    readFileSync(noticePath, 'utf8')
      .split(/\r?\n/)
      .filter((line) => line && !line.startsWith('#') && !line.startsWith('local_path\t'))
      .map((line) => line.split('\t')[0])
  )
}

async function collectFiles(targetPath) {
  const absolutePath = resolve(targetPath)
  const target = statSync(absolutePath)

  if (target.isFile()) {
    return [absolutePath]
  }

  const children = await readdir(absolutePath, { withFileTypes: true })
  const files = await Promise.all(
    children.map(async (child) => {
      const childPath = `${absolutePath}/${child.name}`
      return child.isDirectory() ? collectFiles(childPath) : [childPath]
    })
  )
  return files.flat()
}

async function checkNotices(targetPath) {
  const noticePaths = getNoticePaths()
  const files = await collectFiles(targetPath)
  const missingNotices = files
    .filter((filePath) => grampsDerivedMarker.test(readFileSync(filePath, 'utf8')))
    .map((filePath) => relative(process.cwd(), filePath).split('\\').join('/'))
    .filter((localPath) => !noticePaths.has(localPath))

  if (missingNotices.length > 0) {
    throw new Error(`В NOTICE отсутствуют записи для: ${missingNotices.join(', ')}`)
  }
}

const targetPath = process.argv[2]

if (!targetPath) {
  console.error('Использование: node scripts/check-notices.mjs <путь>')
  process.exitCode = 1
} else {
  checkNotices(targetPath).catch((error) => {
    console.error(error.message)
    process.exitCode = 1
  })
}
