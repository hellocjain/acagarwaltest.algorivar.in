import {
  BookOpen,
  ClipboardList,
  Download,
  ExternalLink,
  Globe,
  HelpCircle,
  Menu,
  Moon,
  Sun,
} from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router'
import { Footer } from '@/components/layout/Footer'
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from '@/components/ui/accordion'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from '@/components/ui/sheet'
import { useThemeStore } from '@/stores/themeStore'

const faqData = [
  {
    category: 'General',
    questions: [
      {
        question: 'What is AC Agarwal Algo?',
        answer:
          'AC Agarwal Algo is an algorithmic trading platform that provides a unified API layer for trading automation. It enables seamless integration with TradingView, Amibroker, Excel, Python, and AI agents, allowing traders to automate their trading strategies with A C Agarwal Share Brokers.',
      },
      {
        question: 'Which brokers are supported?',
        answer:
          'AC Agarwal Algo provides native integration with AC Agarwal trading accounts, alongside unified support for Indian market instruments and automated trading capabilities.',
      },
      {
        question: 'What are the system requirements?',
        answer:
          'AC Agarwal Algo requires Python 3.12 or higher and Node.js 20+ for the frontend. It runs on Windows, macOS, and Linux. For optimal performance, we recommend at least 4GB RAM and a stable internet connection. The application uses SQLite by default, making it lightweight and easy to deploy.',
      },
      {
        question: 'Where can I host AC Agarwal Algo?',
        answer:
          'AC Agarwal Algo can be hosted locally on your personal computer, on a VPS (Virtual Private Server), or in the cloud. Popular options include AWS, Google Cloud, DigitalOcean, or any Linux VPS provider. Hosting on an Indian VPS ensures low latency connections to trading servers.',
      },
    ],
  },
  {
    category: 'Costs & Security',
    questions: [
      {
        question: 'What are the costs involved?',
        answer:
          'There are no hidden software subscription fees for using the AC Agarwal Algo platform. You only pay standard brokerage charges and statutory costs as applicable to your AC Agarwal trading account, plus your VPS hosting costs if self-hosting in the cloud.',
      },
      {
        question: 'How secure is AC Agarwal Algo?',
        answer:
          'Security is a top priority. AC Agarwal Algo stores API credentials locally on your machine with encryption. It uses HTTPS for all communications, implements CSRF protection, rate limiting, and secure session management. Since it runs on your own infrastructure, you have complete control over your data. We recommend using strong passwords and enabling 2FA where available.',
      },
      {
        question: 'Why do I need to login daily?',
        answer:
          'Daily login is required by Indian brokers and exchange guidelines for security compliance. Broker sessions typically expire at the end of each trading day or after a set period (usually around 3 AM IST). This is a regulatory requirement. The platform makes re-authentication quick and easy with TOTP support.',
      },
    ],
  },
  {
    category: 'Features & Integration',
    questions: [
      {
        question: 'Which platforms can I integrate with AC Agarwal Algo?',
        answer:
          'AC Agarwal Algo integrates with TradingView (via webhooks), Amibroker (via AFL), GoCharting, ChartInk, MetaTrader, Excel, Google Sheets, Python, Node.js, Go, N8N, and any platform that can send HTTP webhooks. You can also use the REST API directly from any programming language.',
      },
      {
        question: 'Does AC Agarwal Algo support sandbox trading?',
        answer:
          'Yes! AC Agarwal Algo includes an Analyzer/Sandbox mode with sandbox capital of Rs. 1 Crore. This allows you to test strategies in a realistic environment with proper margin calculations, auto square-off at exchange timings, and complete isolation from live trading. Perfect for testing before going live.',
      },
      {
        question: 'Can I run multiple strategies simultaneously?',
        answer:
          'Yes, AC Agarwal Algo supports running multiple strategies simultaneously. You can create different webhook endpoints for different strategies, manage them independently, and monitor their performance through the dashboard. The Action Center allows you to control execution modes for each strategy.',
      },
      {
        question: 'Does AC Agarwal Algo provide real-time market data?',
        answer:
          'Yes, AC Agarwal Algo includes a unified WebSocket server that streams real-time market data. This data is used for live position tracking, P&L updates, and can be accessed by your strategies.',
      },
      {
        question: 'Can I integrate AC Agarwal Algo with GPT/AI assistants?',
        answer:
          'Yes! AC Agarwal Algo provides REST APIs that can be called from AI assistants, chatbots, or any automated system. You can build AI-powered trading assistants that use AC Agarwal Algo to execute trades based on natural language commands or AI analysis.',
      },
    ],
  },
]

export default function Faq() {
  const { mode, toggleMode } = useThemeStore()
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false)

  const navLinks = [
    { href: '/', label: 'Home', internal: true },
    { href: '/faq', label: 'FAQ', internal: true },
    { href: 'https://board.acagarwal.com', label: 'Client Portal', internal: false },
    { href: 'https://acagarwal.com', label: 'Website', internal: false },
  ]

  return (
    <div className="min-h-screen bg-background flex flex-col">
      {/* Navbar */}
      <header className="sticky top-0 z-30 h-16 w-full border-b bg-background/90 backdrop-blur">
        <nav className="container mx-auto px-4 flex h-full items-center justify-between">
          {/* Logo */}
          <div className="flex items-center gap-2">
            {/* Mobile menu button */}
            <Sheet open={mobileMenuOpen} onOpenChange={setMobileMenuOpen}>
              <SheetTrigger asChild className="lg:hidden">
                <Button variant="ghost" size="icon" aria-label="Open menu">
                  <Menu className="h-5 w-5" />
                </Button>
              </SheetTrigger>
              <SheetContent side="left" className="w-80">
                <SheetHeader className="sr-only">
                  <SheetTitle>Navigation Menu</SheetTitle>
                  <SheetDescription>Main navigation and quick access links</SheetDescription>
                </SheetHeader>
                <div className="flex items-center gap-2 mb-8">
                  <img src="/logo.png" alt="AC Agarwal" className="h-8 w-auto object-contain max-w-[140px]" />
                  <span className="text-xl font-semibold">AC Agarwal</span>
                </div>
                <div className="flex flex-col gap-2">
                  <Link
                    to="/"
                    className="flex items-center gap-2 px-4 py-2 rounded-md hover:bg-accent"
                    onClick={() => setMobileMenuOpen(false)}
                  >
                    <svg
                      xmlns="http://www.w3.org/2000/svg"
                      className="h-5 w-5"
                      fill="none"
                      viewBox="0 0 24 24"
                      stroke="currentColor"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2}
                        d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6"
                      />
                    </svg>
                    Home
                  </Link>
                  <Link
                    to="/faq"
                    className="flex items-center gap-2 px-4 py-2 rounded-md hover:bg-accent"
                    onClick={() => setMobileMenuOpen(false)}
                  >
                    <HelpCircle className="h-5 w-5" />
                    FAQ
                  </Link>
                  <Link
                    to="/download"
                    className="flex items-center gap-2 px-4 py-2 rounded-md bg-primary text-primary-foreground hover:bg-primary/90"
                    onClick={() => setMobileMenuOpen(false)}
                  >
                    <Download className="h-5 w-5" />
                    Download
                  </Link>
                  <a
                    href="https://board.acagarwal.com"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex items-center gap-2 px-4 py-2 rounded-md hover:bg-accent"
                  >
                    <ClipboardList className="h-5 w-5" />
                    Client Portal
                  </a>
                  <a
                    href="https://acagarwal.com"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex items-center gap-2 px-4 py-2 rounded-md hover:bg-accent"
                  >
                    <BookOpen className="h-5 w-5" />
                    Website
                  </a>
                </div>
              </SheetContent>
            </Sheet>

            <Link to="/" className="flex items-center gap-2">
              <img src="/logo.png" alt="AC Agarwal" className="h-8 w-auto object-contain max-w-[140px]" />
              <span className="text-xl font-bold hidden sm:inline">AC Agarwal</span>
            </Link>
          </div>

          {/* Desktop Navigation */}
          <div className="hidden lg:flex items-center gap-1">
            {navLinks.map((link) =>
              link.internal ? (
                <Link key={link.href} to={link.href}>
                  <Button variant="ghost" size="sm">
                    {link.label}
                  </Button>
                </Link>
              ) : (
                <a key={link.href} href={link.href} target="_blank" rel="noopener noreferrer">
                  <Button variant="ghost" size="sm">
                    {link.label}
                  </Button>
                </a>
              )
            )}
          </div>

          {/* Right side */}
          <div className="flex items-center gap-2">
            <Link to="/download">
              <Button size="sm">Download</Button>
            </Link>
            <Button
              variant="ghost"
              size="icon"
              onClick={toggleMode}
              aria-label={mode === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
            >
              {mode === 'dark' ? <Sun className="h-5 w-5" /> : <Moon className="h-5 w-5" />}
            </Button>
          </div>
        </nav>
      </header>

      {/* Main Content */}
      <main className="flex-1">
        <div className="container mx-auto px-4 py-12">
          {/* Header */}
          <div className="text-center mb-12">
            <h1 className="text-4xl lg:text-5xl font-bold mb-4">Frequently Asked Questions</h1>
            <p className="text-lg text-muted-foreground max-w-2xl mx-auto">
              Find answers to common questions about OpenAlgo, its features, security, and
              licensing.
            </p>
          </div>

          {/* FAQ Categories */}
          <div className="max-w-4xl mx-auto space-y-8">
            {faqData.map((category) => (
              <Card key={category.category}>
                <CardHeader>
                  <CardTitle>{category.category}</CardTitle>
                  <CardDescription>
                    {category.category === 'General' && 'Basic information about OpenAlgo'}
                    {category.category === 'Costs & Security' &&
                      'Pricing, security, and compliance details'}
                    {category.category === 'Features & Integration' &&
                      'Platform capabilities and integrations'}
                    {category.category === 'Licensing & Usage' &&
                      'License terms and usage guidelines'}
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <Accordion type="single" collapsible className="w-full">
                    {category.questions.map((faq, index) => (
                      <AccordionItem key={index} value={`${category.category}-${index}`}>
                        <AccordionTrigger className="text-left">{faq.question}</AccordionTrigger>
                        <AccordionContent className="text-muted-foreground">
                          {faq.answer}
                        </AccordionContent>
                      </AccordionItem>
                    ))}
                  </Accordion>
                </CardContent>
              </Card>
            ))}
          </div>

          {/* Resources Section */}
          <div className="max-w-4xl mx-auto mt-16">
            <h2 className="text-2xl font-bold text-center mb-8">Need More Help?</h2>
            <div className="grid md:grid-cols-3 gap-6">
              <Card className="text-center">
                <CardHeader>
                  <BookOpen className="h-10 w-10 mx-auto text-primary" />
                  <CardTitle className="text-lg">Website</CardTitle>
                </CardHeader>
                <CardContent>
                  <p className="text-sm text-muted-foreground mb-4">
                    Product guides and company information
                  </p>
                  <Button variant="outline" asChild>
                    <a href="https://acagarwal.com" target="_blank" rel="noopener noreferrer">
                      Visit Website
                    </a>
                  </Button>
                </CardContent>
              </Card>

              <Card className="text-center">
                <CardHeader>
                  <ExternalLink className="h-10 w-10 mx-auto text-primary" />
                  <CardTitle className="text-lg">Client Portal</CardTitle>
                </CardHeader>
                <CardContent>
                  <p className="text-sm text-muted-foreground mb-4">
                    Access backoffice, reports and accounts
                  </p>
                  <Button variant="outline" asChild>
                    <a href="https://board.acagarwal.com" target="_blank" rel="noopener noreferrer">
                      Open Portal
                    </a>
                  </Button>
                </CardContent>
              </Card>

              <Card className="text-center">
                <CardHeader>
                  <Globe className="h-10 w-10 mx-auto text-primary" />
                  <CardTitle className="text-lg">Support</CardTitle>
                </CardHeader>
                <CardContent>
                  <p className="text-sm text-muted-foreground mb-4">
                    Reach our dedicated customer support team
                  </p>
                  <Button variant="outline" asChild>
                    <a
                      href="https://acagarwal.com/contact-us"
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      Contact Support
                    </a>
                  </Button>
                </CardContent>
              </Card>
            </div>
          </div>
        </div>
      </main>

      {/* Footer */}
      <Footer />
    </div>
  )
}
