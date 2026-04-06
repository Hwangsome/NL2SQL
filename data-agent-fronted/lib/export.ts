/**
 * 将数据导出为 CSV 格式并下载
 */
export function exportToCsv(data: Record<string, unknown>[], filename = "export.csv"): void {
  if (data.length === 0) {
    return
  }

  // 获取所有列名
  const headers = Object.keys(data[0])
  
  // 构建 CSV 内容
  const csvRows: string[] = []
  
  // 添加表头
  csvRows.push(headers.map(escapeCSVValue).join(","))
  
  // 添加数据行
  for (const row of data) {
    const values = headers.map(header => {
      const value = row[header]
      return escapeCSVValue(String(value ?? ""))
    })
    csvRows.push(values.join(","))
  }
  
  const csvContent = csvRows.join("\n")
  
  // 添加 BOM 以支持中文在 Excel 中正确显示
  const bom = "\uFEFF"
  const blob = new Blob([bom + csvContent], { type: "text/csv;charset=utf-8" })
  
  // 创建下载链接
  const url = URL.createObjectURL(blob)
  const link = document.createElement("a")
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  URL.revokeObjectURL(url)
}

/**
 * 转义 CSV 值中的特殊字符
 */
function escapeCSVValue(value: string): string {
  // 如果值包含逗号、双引号或换行符，需要用双引号包裹
  if (value.includes(",") || value.includes('"') || value.includes("\n")) {
    // 将双引号转义为两个双引号
    return `"${value.replace(/"/g, '""')}"`
  }
  return value
}

/**
 * 复制 JSON 数据到剪贴板
 */
export async function copyJson(data: unknown): Promise<boolean> {
  try {
    const jsonString = JSON.stringify(data, null, 2)
    await navigator.clipboard.writeText(jsonString)
    return true
  } catch {
    // 降级方案：使用 document.execCommand
    try {
      const textarea = document.createElement("textarea")
      textarea.value = JSON.stringify(data, null, 2)
      textarea.style.position = "fixed"
      textarea.style.opacity = "0"
      document.body.appendChild(textarea)
      textarea.select()
      document.execCommand("copy")
      document.body.removeChild(textarea)
      return true
    } catch {
      return false
    }
  }
}
