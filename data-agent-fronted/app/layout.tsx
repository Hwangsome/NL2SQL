import type { Metadata, Viewport } from 'next'
import { Analytics } from '@vercel/analytics/next'
import './globals.css'

export const metadata: Metadata = {
  title: '掌柜问数 - 用自然语言查询业务数据',
  description: '智能数据问答平台，用自然语言查询业务数据，AI驱动的NL2SQL解决方案',
  keywords: ['NL2SQL', '数据查询', '自然语言处理', 'AI数据分析'],
}

export const viewport: Viewport = {
  themeColor: '#1a2634',
  width: 'device-width',
  initialScale: 1,
}

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode
}>) {
  return (
    <html lang="zh-CN">
      <body className="font-sans antialiased">
        {children}
        {process.env.NODE_ENV === 'production' && <Analytics />}
      </body>
    </html>
  )
}
