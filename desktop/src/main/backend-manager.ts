import { ChildProcess, spawn } from 'child_process'
import { EventEmitter } from 'events'
import { existsSync } from 'fs'
import { join } from 'path'

export interface BackendConfig {
  port: number
  projectRoot: string
  apiKey?: string
  initLlm?: boolean
  lmModelPath?: string
  noInit?: boolean
  pythonPath?: string
  environment?: Record<string, string>
}

export interface BackendStatus {
  status: 'stopped' | 'starting' | 'healthy' | 'unhealthy' | 'error'
  error?: string
  port?: number
  pid?: number
}

export class BackendManager extends EventEmitter {
  private process: ChildProcess | null = null
  private healthCheckInterval: ReturnType<typeof setInterval> | null = null
  private restartAttempts = 0
  private config: BackendConfig | null = null
  private _status: BackendStatus = { status: 'stopped' }
  private logBuffer: string[] = []
  private readonly MAX_LOG_LINES = 500
  private readonly MAX_RESTART_ATTEMPTS = 3

  get status(): BackendStatus {
    return this._status
  }

  private setStatus(status: BackendStatus): void {
    this._status = status
    this.emit('status-changed', status)
  }

  async start(config: BackendConfig): Promise<void> {
    if (this.process) {
      await this.stop()
    }

    this.config = config
    this.restartAttempts = 0
    this.setStatus({ status: 'starting', port: config.port })

    await this.spawnProcess()
  }

  private async spawnProcess(): Promise<void> {
    if (!this.config) throw new Error('No backend config')

    const pythonPath = this.resolvePython(this.config)
    const args = this.buildArgs(this.config, pythonPath)

    this.emitLog(`Starting backend: ${pythonPath} ${args.join(' ')}`)

    const env: NodeJS.ProcessEnv = {
      ...process.env,
      ACESTEP_API_HOST: '127.0.0.1',
      ACESTEP_API_PORT: String(this.config.port),
      ...(this.config.environment || {})
    }

    if (this.config.apiKey) {
      env.ACESTEP_API_KEY = this.config.apiKey
    }

    this.process = spawn(pythonPath, args, {
      cwd: this.config.projectRoot,
      env,
      stdio: ['ignore', 'pipe', 'pipe'],
      windowsHide: true
    })

    this.process.stdout?.on('data', (data: Buffer) => {
      this.emitLog(data.toString())
    })

    this.process.stderr?.on('data', (data: Buffer) => {
      this.emitLog(data.toString())
    })

    this.process.on('error', (err) => {
      this.emitLog(`Backend process error: ${err.message}`)
      this.setStatus({ status: 'error', error: err.message })
    })

    this.process.on('exit', (code, signal) => {
      this.emitLog(`Backend exited: code=${code}, signal=${signal}`)
      this.process = null
      this.stopHealthChecks()

      if (this._status.status !== 'stopped') {
        this.handleUnexpectedExit()
      }
    })

    // Wait for health check to pass
    try {
      await this.waitForHealthy(120_000) // 120s timeout for model loading
      this.restartAttempts = 0
      this.setStatus({ status: 'healthy', port: this.config.port, pid: this.process?.pid })
      this.startHealthChecks()
    } catch (err) {
      this.emitLog(`Backend failed to become healthy: ${err}`)
      if (this.process) {
        this.process.kill('SIGTERM')
        this.process = null
      }
      this.setStatus({ status: 'error', error: String(err) })
    }
  }

  private resolvePython(config: BackendConfig): string {
    // 1. User-specified path
    if (config.pythonPath && existsSync(config.pythonPath)) {
      return config.pythonPath
    }

    // 2. Bundled embedded Python
    const bundledPython = join(__dirname, '../../resources/backend/python/python.exe')
    if (existsSync(bundledPython)) {
      return bundledPython
    }

    // 3. Fall back to uv (expects it in PATH)
    return 'uv'
  }

  private buildArgs(config: BackendConfig, pythonPath: string): string[] {
    const isUv = pythonPath === 'uv'

    const args: string[] = isUv
      ? ['run', 'acestep-api']
      : ['-m', 'acestep.api.server_cli']

    args.push('--host', '127.0.0.1')
    args.push('--port', String(config.port))

    if (config.apiKey) args.push('--api-key', config.apiKey)
    if (config.noInit) args.push('--no-init')
    if (config.initLlm) args.push('--init-llm')
    if (config.lmModelPath) args.push('--lm-model-path', config.lmModelPath)

    return args
  }

  private async waitForHealthy(timeoutMs: number): Promise<void> {
    const start = Date.now()
    const port = this.config?.port || 8001

    while (Date.now() - start < timeoutMs) {
      if (!this.process) throw new Error('Backend process died during startup')

      try {
        const controller = new AbortController()
        const timeout = setTimeout(() => controller.abort(), 3000)
        const res = await fetch(`http://127.0.0.1:${port}/health`, {
          signal: controller.signal
        })
        clearTimeout(timeout)
        if (res.ok) return
      } catch {
        // Server not ready yet
      }

      await new Promise((r) => setTimeout(r, 2000))
    }

    throw new Error(`Backend did not become healthy within ${timeoutMs / 1000}s`)
  }

  private startHealthChecks(): void {
    this.stopHealthChecks()
    const port = this.config?.port || 8001

    this.healthCheckInterval = setInterval(async () => {
      try {
        const controller = new AbortController()
        const timeout = setTimeout(() => controller.abort(), 5000)
        const res = await fetch(`http://127.0.0.1:${port}/health`, {
          signal: controller.signal
        })
        clearTimeout(timeout)

        if (res.ok) {
          if (this._status.status !== 'healthy') {
            this.setStatus({ status: 'healthy', port, pid: this.process?.pid })
          }
        } else {
          this.setStatus({ status: 'unhealthy', port })
        }
      } catch {
        if (this._status.status === 'healthy') {
          this.setStatus({ status: 'unhealthy', port })
        }
      }
    }, 5000)
  }

  private stopHealthChecks(): void {
    if (this.healthCheckInterval) {
      clearInterval(this.healthCheckInterval)
      this.healthCheckInterval = null
    }
  }

  private handleUnexpectedExit(): void {
    if (this.restartAttempts < this.MAX_RESTART_ATTEMPTS && this.config) {
      this.restartAttempts++
      this.emitLog(`Restarting backend (attempt ${this.restartAttempts}/${this.MAX_RESTART_ATTEMPTS})...`)
      this.setStatus({ status: 'starting' })
      this.spawnProcess().catch((err) => {
        this.setStatus({ status: 'error', error: String(err) })
      })
    } else {
      this.setStatus({
        status: 'error',
        error: `Backend crashed after ${this.MAX_RESTART_ATTEMPTS} restart attempts`
      })
    }
  }

  async stop(): Promise<void> {
    this.stopHealthChecks()
    this.setStatus({ status: 'stopped' })

    if (!this.process) return

    this.emitLog('Stopping backend...')

    return new Promise<void>((resolve) => {
      const timeout = setTimeout(() => {
        this.emitLog('Force-killing backend (timeout)')
        this.process?.kill('SIGKILL')
        this.process = null
        resolve()
      }, 5000)

      this.process!.on('exit', () => {
        clearTimeout(timeout)
        this.process = null
        this.emitLog('Backend stopped')
        resolve()
      })

      this.process!.kill('SIGTERM')
    })
  }

  private emitLog(text: string): void {
    const lines = text.split('\n').filter((l) => l.trim())
    for (const line of lines) {
      this.logBuffer.push(line)
      if (this.logBuffer.length > this.MAX_LOG_LINES) {
        this.logBuffer.shift()
      }
      this.emit('log', line)
    }
  }

  getLogs(): string[] {
    return [...this.logBuffer]
  }
}
