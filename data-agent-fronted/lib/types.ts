// SSE 事件类型定义

export type ProgressStatus = "running" | "success" | "error"

export type ProgressEvent = {
  type: "progress"
  step: string
  status: ProgressStatus
  detail?: string
}

export type AnswerEvent = {
  type: "answer"
  delta: string
}

export type ResultEvent = {
  type: "result"
  data: Record<string, unknown>[]
  answer?: string
  sql?: string
}

export type ErrorEvent = {
  type: "error"
  message: string
}

export type StreamEvent = ProgressEvent | AnswerEvent | ResultEvent | ErrorEvent

// 应用状态类型
export type ConnectionStatus = "checking" | "connected" | "disconnected"

export interface ProgressStep {
  step: string
  status: ProgressStatus
  detail?: string
}

export interface ConversationTurn {
  id: string
  query: string
  progressSteps: ProgressStep[]
  answer: string
  resultRows: Record<string, unknown>[]
  sql?: string
  errorMessage: string
  isStreaming: boolean
}

// API 响应类型
export interface HealthResponse {
  status: "ok"
}
