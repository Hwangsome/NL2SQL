import type { StreamEvent } from "./types"

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8000"

/**
 * POST SSE 流式查询处理器
 * 手动实现 SSE 解析，处理 chunk 边界问题
 */
export async function streamQuery(
  query: string,
  onEvent: (event: StreamEvent) => void,
  signal?: AbortSignal
): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/api/query`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "text/event-stream",
    },
    body: JSON.stringify({ query }),
    signal,
    cache: "no-store",
  })

  if (!response.ok) {
    throw new Error(`HTTP error! status: ${response.status}`)
  }

  if (!response.body) {
    throw new Error("Response body is null")
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder("utf-8")
  
  // 缓冲区，用于处理跨 chunk 的数据
  let buffer = ""

  try {
    while (true) {
      const { done, value } = await reader.read()
      
      if (done) {
        // 流结束，处理缓冲区中剩余的数据
        if (buffer.trim()) {
          processBuffer(buffer, onEvent)
        }
        break
      }

      // 将新数据追加到缓冲区
      buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, "\n")
      
      // 按照 SSE 规范，事件以 \n\n 分隔
      const eventBlocks = buffer.split("\n\n")
      
      // 保留最后一个可能不完整的块
      buffer = eventBlocks.pop() || ""
      
      // 处理完整的事件块
      for (const block of eventBlocks) {
        if (block.trim()) {
          processEventBlock(block, onEvent)
        }
      }
    }
  } finally {
    reader.releaseLock()
  }
}

/**
 * 处理单个 SSE 事件块
 */
function processEventBlock(block: string, onEvent: (event: StreamEvent) => void): void {
  const lines = block.split("\n")
  
  for (const line of lines) {
    // 只处理 data: 开头的行
    if (line.startsWith("data:")) {
      const jsonStr = line.slice(5).trim() // 去掉 "data:" 前缀
      
      if (jsonStr) {
        try {
          const event = JSON.parse(jsonStr) as StreamEvent
          onEvent(event)
        } catch (e) {
          console.error("[v0] Failed to parse SSE data:", jsonStr, e)
        }
      }
    }
  }
}

/**
 * 处理缓冲区中剩余的数据
 */
function processBuffer(buffer: string, onEvent: (event: StreamEvent) => void): void {
  const blocks = buffer.split("\n\n")
  for (const block of blocks) {
    if (block.trim()) {
      processEventBlock(block, onEvent)
    }
  }
}

/**
 * 检查后端健康状态
 */
export async function checkHealth(): Promise<boolean> {
  try {
    const response = await fetch(`${API_BASE_URL}/health`, {
      method: "GET",
      signal: AbortSignal.timeout(5000),
    })
    
    if (!response.ok) {
      return false
    }
    
    const data = await response.json()
    return data.status === "ok"
  } catch {
    return false
  }
}
