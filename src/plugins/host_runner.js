/**
 * Kototsuna Plugin Host Runner
 *
 * わんコメ互換の plugin.js をロードして Python 側と JSON-Lines (stdin/stdout) で通信する
 * Node.js ホストスクリプト。
 *
 * Python → Node (stdin, 1行 = 1 JSON):
 *   { "type": "init",      "id": "...", "data": {} }
 *   { "type": "comment",   "id": "...", "comment": {...}, "service": "...", "userData": null }
 *   { "type": "subscribe", "id": "...", "event": "comments", "data": {...} }
 *   { "type": "shutdown" }
 *
 * Node → Python (stdout, 1行 = 1 JSON):
 *   { "type": "ready",         "id": "...", "name": "...", "uid": "...", "version": "..." }
 *   { "type": "filter_result", "id": "...", "result": <comment|false> }
 *   { "type": "subscribed",    "id": "..." }
 *   { "type": "error",         "id": "...", "message": "..." }
 *   { "type": "log",           "level": "info", "message": "..." }
 */

'use strict'

const path = require('path')
const fs = require('fs')
const readline = require('readline')
const os = require('os')

const pluginPath = process.argv[2]
if (!pluginPath) {
  process.stderr.write('Usage: node host_runner.js <plugin.js path>\n')
  process.exit(1)
}

// ─── ElectronStore 互換シム ────────────────────────────────────────
class StoreShim {
  constructor(uid) {
    const appdata = process.env.APPDATA || path.join(os.homedir(), 'AppData', 'Roaming')
    const storeDir = path.join(appdata, 'Kototsuna', 'plugin-store')
    this._file = path.join(storeDir, `${uid.replace(/[^a-zA-Z0-9._-]/g, '_')}.json`)
    this._data = {}
    this._load()
  }

  _load() {
    try { this._data = JSON.parse(fs.readFileSync(this._file, 'utf8')) } catch (_) {}
  }

  _save() {
    try {
      fs.mkdirSync(path.dirname(this._file), { recursive: true })
      fs.writeFileSync(this._file, JSON.stringify(this._data, null, 2))
    } catch (_) {}
  }

  get(key, defaultValue) { return key in this._data ? this._data[key] : defaultValue }
  set(key, value)        { this._data[key] = value; this._save() }
  delete(key)            { delete this._data[key]; this._save() }
  has(key)               { return key in this._data }
}

// ─── stdout 書き出し ───────────────────────────────────────────────
function send(obj) {
  process.stdout.write(JSON.stringify(obj) + '\n')
}

// ─── プラグイン本体 ────────────────────────────────────────────────
let plugin = null

async function handleMessage(msg) {
  const { type, id } = msg
  try {
    switch (type) {

      case 'init': {
        plugin = require(path.resolve(pluginPath))
        const store = new StoreShim(plugin.uid || path.basename(path.dirname(pluginPath)))
        if (typeof plugin.init === 'function') {
          await plugin.init(
            { dir: path.dirname(pluginPath), filepath: pluginPath, store },
            msg.data || {}
          )
        }
        send({ type: 'ready', id,
               name: plugin.name || '', uid: plugin.uid || '',
               version: plugin.version || '' })
        break
      }

      case 'comment': {
        const { comment, service, userData } = msg
        let result = comment
        if (plugin && typeof plugin.filterComment === 'function') {
          result = await plugin.filterComment(comment, service, userData || null)
        }
        // undefined は「変更なし」として扱う
        send({ type: 'filter_result', id, result: result === undefined ? comment : result })
        break
      }

      case 'subscribe': {
        const { event, data } = msg
        if (plugin && typeof plugin.subscribe === 'function') {
          await plugin.subscribe(event, data)
        }
        send({ type: 'subscribed', id })
        break
      }

      case 'shutdown': {
        if (plugin && typeof plugin.destroy === 'function') {
          await plugin.destroy()
        }
        process.exit(0)
        break
      }

      default:
        send({ type: 'error', id, message: `Unknown message type: ${type}` })
    }
  } catch (err) {
    send({ type: 'error', id, message: String(err.message || err) })
  }
}

// ─── stdin 読み込みループ ──────────────────────────────────────────
const rl = readline.createInterface({ input: process.stdin, crlfDelay: Infinity })

rl.on('line', (line) => {
  const trimmed = line.trim()
  if (!trimmed) return
  try {
    const msg = JSON.parse(trimmed)
    handleMessage(msg)
  } catch (err) {
    send({ type: 'error', message: `JSON parse error: ${err.message}` })
  }
})

rl.on('close', () => {
  // stdin が閉じられたら終了
  if (plugin && typeof plugin.destroy === 'function') {
    Promise.resolve(plugin.destroy()).finally(() => process.exit(0))
  } else {
    process.exit(0)
  }
})
