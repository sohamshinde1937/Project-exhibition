"use client";

import { useCallback, useState, type FormEvent, type ReactNode } from "react";
import {
  Award,
  BadgeCheck,
  Bot,
  BrushCleaning,
  Check,
  ChevronDown,
  CircleCheck,
  ClipboardCheck,
  Clock,
  Droplets,
  House,
  MapPin,
  Menu,
  PhoneCall,
  ReceiptIndianRupee,
  ShieldCheck,
  Star,
  Wrench,
  X,
  Zap,
} from "lucide-react";
import AICallModal from "@/components/AICallModal";

// ─────────────────────────────────────────────────────────────────────────────
// Content
// ─────────────────────────────────────────────────────────────────────────────
const SERVICE_AREAS = [
  "Pune",
  "Pimpri-Chinchwad",
  "Hinjewadi",
  "Kothrud",
  "Baner",
  "Wakad",
  "Hadapsar",
  "Kharadi",
  "Viman Nagar",
  "Chakan",
];

const TESTIMONIALS = [
  {
    name: "Priya Deshmukh",
    area: "Kothrud, Pune",
    when: "2 weeks ago",
    initials: "PD",
    text: "Pipe burst at 11 pm during the monsoon. The AI dispatcher picked up instantly, understood it was an emergency and a plumber was at my door within the hour. Clear price before any work started.",
  },
  {
    name: "Rahul Kulkarni",
    area: "Wakad, Pimpri-Chinchwad",
    when: "1 month ago",
    initials: "RK",
    text: "Booked a free roof inspection just by talking to their assistant. The crew found two cracked sheets, quoted upfront and left the terrace cleaner than they found it. Genuinely professional.",
  },
];

const STEPS = [
  {
    icon: PhoneCall,
    title: "You Contact Us",
    text: "Tap any Call button. No dialling, no hold music: you are talking to our dispatcher in your browser within seconds.",
  },
  {
    icon: Bot,
    title: "AI Dispatch & Routing",
    text: "Ava, our AI receptionist, understands the problem and transfers you to sales for quotes or to emergency support for leaks and breakdowns.",
    highlight: true,
  },
  {
    icon: ClipboardCheck,
    title: "On-Site Assessment",
    text: "A licensed technician arrives on time, inspects the root cause and explains exactly what they found.",
  },
  {
    icon: ReceiptIndianRupee,
    title: "Upfront Pricing",
    text: "You approve a fixed price before any work begins. The number we quote is the number you pay.",
  },
  {
    icon: Wrench,
    title: "Quality Service",
    text: "Workmanship backed by warranty, using branded materials suited to Maharashtra's heavy monsoon.",
  },
  {
    icon: BrushCleaning,
    title: "Clean Up",
    text: "We protect your floors, clear every scrap of debris and leave your home as tidy as we found it.",
  },
];

const PROMISES = [
  { title: "Upfront pricing", text: "A fixed, written price agreed before we lift a tool." },
  { title: "No hidden costs", text: "No surprise call-out, overtime or 'materials' add-ons on the bill." },
  { title: "Fully licensed", text: "Licensed and insured technicians; documents available on request." },
  { title: "Clean and respectful", text: "Shoe covers, drop sheets and a full clean-up on every job." },
];

// Mirrors the FAQ the AI receptionist answers on the phone (agent.py).
const FAQS = [
  {
    q: "When can I reach you?",
    a: "Our office is open 8am to 6pm, Monday to Saturday. Emergency dispatch answers 24/7, including Sundays and holidays.",
  },
  {
    q: "Do you charge for estimates?",
    a: "Roofing estimates are free and done in person. Plumbing visits carry a small diagnostic fee that is waived when you go ahead with the repair.",
  },
  {
    q: "How do I pay?",
    a: "Cash, cheque and all major cards. Financing is available for larger roofing projects.",
  },
  {
    q: "Is the voice on the Call button a real person?",
    a: "No. It is Ava, our AI receptionist. She handles the first conversation and routes you to the right specialist instantly, any time of day.",
  },
];

// ─────────────────────────────────────────────────────────────────────────────
// Page
// ─────────────────────────────────────────────────────────────────────────────
export default function Home() {
  const [isModalOpen, setIsModalOpen] = useState(false);
  const openCall = useCallback(() => setIsModalOpen(true), []);
  const closeCall = useCallback(() => setIsModalOpen(false), []);

  return (
    <>
      <Navbar onCall={openCall} />

      <main className="flex-1">
        <Hero onCall={openCall} />
        <TrustBar />
        <Testimonials onCall={openCall} />
        <Process onCall={openCall} />
        <WhyChooseUs onCall={openCall} />
        <FinalCta onCall={openCall} />
      </main>

      <Footer onCall={openCall} />

      {/* Sticky mobile call bar */}
      <div className="fixed inset-x-0 bottom-0 z-40 border-t border-slate-200 bg-white/90 p-3 backdrop-blur md:hidden">
        <CallButton onClick={openCall} className="w-full">
          Call 24/7 AI Dispatch
        </CallButton>
      </div>

      <AICallModal isOpen={isModalOpen} onClose={closeCall} />
    </>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Shared bits
// ─────────────────────────────────────────────────────────────────────────────
function CallButton({
  onClick,
  children,
  className = "",
  size = "md",
  pulse = false,
}: {
  onClick: () => void;
  children: ReactNode;
  className?: string;
  size?: "sm" | "md" | "lg";
  pulse?: boolean;
}) {
  const sizes = {
    sm: "px-4 py-2 text-sm",
    md: "px-6 py-3 text-sm sm:text-base",
    lg: "px-8 py-4 text-base sm:text-lg",
  };
  return (
    <button
      type="button"
      onClick={onClick}
      className={`group relative inline-flex items-center justify-center gap-2.5 rounded-full bg-red-600 font-bold text-white shadow-lg shadow-red-600/30 transition hover:-translate-y-0.5 hover:bg-red-500 hover:shadow-xl hover:shadow-red-600/40 focus:outline-none focus-visible:ring-4 focus-visible:ring-red-500/40 active:translate-y-0 ${sizes[size]} ${className}`}
    >
      {pulse && <span aria-hidden className="absolute inset-0 -z-10 animate-ping rounded-full bg-red-500/40 [animation-duration:2.2s]" />}
      <PhoneCall className="h-[1.1em] w-[1.1em] transition group-hover:rotate-12" />
      {children}
    </button>
  );
}

function SectionLabel({ children, dark = false }: { children: ReactNode; dark?: boolean }) {
  return (
    <p className={`text-xs font-bold uppercase tracking-[0.2em] ${dark ? "text-red-400" : "text-red-600"}`}>{children}</p>
  );
}

function Stars({ className = "h-4 w-4" }: { className?: string }) {
  return (
    <div className="flex gap-0.5" aria-label="5 out of 5 stars">
      {Array.from({ length: 5 }).map((_, i) => (
        <Star key={i} className={`${className} fill-amber-400 text-amber-400`} />
      ))}
    </div>
  );
}

function GoogleG({ className = "h-5 w-5" }: { className?: string }) {
  return (
    <svg viewBox="0 0 48 48" className={className} aria-label="Google">
      <path fill="#FFC107" d="M43.6 20.5H42V20H24v8h11.3C33.7 32.7 29.2 36 24 36c-6.6 0-12-5.4-12-12s5.4-12 12-12c3.1 0 5.8 1.2 7.9 3.1l5.7-5.7C34 6.1 29.3 4 24 4 12.9 4 4 12.9 4 24s8.9 20 20 20 20-8.9 20-20c0-1.3-.1-2.4-.4-3.5z" />
      <path fill="#FF3D00" d="m6.3 14.7 6.6 4.8C14.7 15.1 19 12 24 12c3.1 0 5.8 1.2 7.9 3.1l5.7-5.7C34 6.1 29.3 4 24 4 16.3 4 9.7 8.3 6.3 14.7z" />
      <path fill="#4CAF50" d="M24 44c5.2 0 9.9-2 13.4-5.2l-6.2-5.2c-2 1.5-4.5 2.4-7.2 2.4-5.2 0-9.6-3.3-11.3-7.9l-6.5 5C9.5 39.6 16.2 44 24 44z" />
      <path fill="#1976D2" d="M43.6 20.5H42V20H24v8h11.3c-.8 2.2-2.2 4.2-4.1 5.6l6.2 5.2C37 39.2 44 34 44 24c0-1.3-.1-2.4-.4-3.5z" />
    </svg>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Section 1: Navbar & Hero
// ─────────────────────────────────────────────────────────────────────────────
function Navbar({ onCall }: { onCall: () => void }) {
  const [open, setOpen] = useState(false);
  const links = [
    ["Reviews", "#reviews"],
    ["Our Process", "#process"],
    ["Why Us", "#why-us"],
    ["FAQ", "#faq"],
  ];
  return (
    <header className="sticky top-0 z-40 border-b border-white/10 bg-slate-900/95 text-white backdrop-blur">
      <div className="hidden bg-red-600 text-center text-xs font-semibold tracking-wide sm:block">
        <p className="mx-auto max-w-7xl px-4 py-1.5">
          Monsoon leak? Burst pipe? Emergency dispatch answers 24/7 across the Pune region.
        </p>
      </div>
      <nav className="mx-auto flex max-w-7xl items-center justify-between gap-6 px-4 py-4 sm:px-6 lg:px-8">
        <a href="#" className="flex items-center gap-3">
          <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-red-500 to-red-700 shadow-lg shadow-red-900/40">
            <House className="h-5 w-5" strokeWidth={2.5} />
          </span>
          <span className="leading-tight">
            <span className="block text-lg font-extrabold tracking-tight">SUMMIT</span>
            <span className="block text-[10px] font-semibold uppercase tracking-[0.25em] text-slate-400">
              Roofing &amp; Plumbing
            </span>
          </span>
        </a>

        <div className="hidden items-center gap-8 text-sm font-medium text-slate-300 lg:flex">
          {links.map(([label, href]) => (
            <a key={href} href={href} className="transition hover:text-white">
              {label}
            </a>
          ))}
        </div>

        <div className="flex items-center gap-3">
          <div className="hidden sm:block">
            <CallButton onClick={onCall} size="sm">
              Call 24/7 AI Dispatch
            </CallButton>
          </div>
          <button
            type="button"
            onClick={() => setOpen((o) => !o)}
            className="rounded-lg p-2 text-slate-300 hover:bg-white/10 lg:hidden"
            aria-label="Toggle menu"
            aria-expanded={open}
          >
            {open ? <X className="h-6 w-6" /> : <Menu className="h-6 w-6" />}
          </button>
        </div>
      </nav>
      {open && (
        <div className="border-t border-white/10 px-4 pb-4 lg:hidden">
          {links.map(([label, href]) => (
            <a
              key={href}
              href={href}
              onClick={() => setOpen(false)}
              className="block rounded-lg px-3 py-3 text-slate-200 hover:bg-white/5"
            >
              {label}
            </a>
          ))}
        </div>
      )}
    </header>
  );
}

function Hero({ onCall }: { onCall: () => void }) {
  return (
    <section className="relative overflow-hidden bg-slate-900 text-white">
      {/* Background: grid + glows */}
      <div aria-hidden className="pointer-events-none absolute inset-0">
        <div className="absolute inset-0 bg-[linear-gradient(rgba(255,255,255,0.04)_1px,transparent_1px),linear-gradient(90deg,rgba(255,255,255,0.04)_1px,transparent_1px)] bg-[size:48px_48px] [mask-image:radial-gradient(ellipse_at_top_left,black,transparent_70%)]" />
        <div className="absolute -left-40 top-10 h-[30rem] w-[30rem] rounded-full bg-red-600/20 blur-[120px]" />
        <div className="absolute -right-20 bottom-0 h-[26rem] w-[26rem] rounded-full bg-blue-500/15 blur-[120px]" />
      </div>

      <div className="relative mx-auto grid max-w-7xl items-center gap-12 px-4 py-16 sm:px-6 md:py-24 lg:grid-cols-[1.15fr_1fr] lg:gap-16 lg:px-8">
        {/* Left */}
        <div>
          <span className="inline-flex items-center gap-2 rounded-full border border-red-500/40 bg-red-600/15 px-4 py-1.5 text-sm font-bold text-red-300">
            <Zap className="h-4 w-4 fill-red-400 text-red-400" />
            ₹0 Plumbing Call-Out*
          </span>

          <h1 className="mt-6 text-4xl font-extrabold leading-[1.05] tracking-tight sm:text-5xl lg:text-6xl">
            Plumbing &amp; Roofing
            <span className="block bg-gradient-to-r from-red-500 via-red-400 to-orange-300 bg-clip-text text-transparent">
              You Can Rely On
            </span>
          </h1>

          <p className="mt-6 max-w-xl text-lg leading-relaxed text-slate-300">
            Licensed local technicians for leaks, blockages, roof repairs and full re-roofs. Our AI dispatcher picks up
            every call instantly, day or night, and routes it to the right expert.
          </p>

          <div className="mt-8 flex flex-col gap-4 sm:flex-row sm:items-center">
            <CallButton onClick={onCall} size="lg" pulse>
              Call 24/7 AI Dispatch
            </CallButton>
            <div className="flex items-center gap-3">
              <Stars />
              <span className="text-sm text-slate-300">
                <strong className="text-white">4.9</strong> from local Google reviews
              </span>
            </div>
          </div>

          <div className="mt-10">
            <p className="flex items-center gap-2 text-sm font-semibold uppercase tracking-widest text-slate-400">
              <MapPin className="h-4 w-4 text-red-500" />
              Serving across Maharashtra
            </p>
            <ul className="mt-4 flex flex-wrap gap-2">
              {SERVICE_AREAS.map((area) => (
                <li
                  key={area}
                  className="rounded-full border border-white/10 bg-white/5 px-3 py-1 text-sm text-slate-200"
                >
                  {area}
                </li>
              ))}
            </ul>
          </div>

          <p className="mt-6 text-xs text-slate-500">
            *Diagnostic call-out fee is waived when you go ahead with the repair.
          </p>
        </div>

        {/* Right: quote card */}
        <QuoteCard onCall={onCall} />
      </div>
    </section>
  );
}

function QuoteCard({ onCall }: { onCall: () => void }) {
  const submit = (e: FormEvent) => {
    e.preventDefault();
    // Demo: the AI dispatcher takes the details by voice instead of a callback queue.
    onCall();
  };

  const input =
    "w-full rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-slate-900 placeholder:text-slate-400 transition focus:border-red-500 focus:bg-white focus:outline-none focus:ring-4 focus:ring-red-500/15";

  return (
    <div className="relative">
      <div aria-hidden className="absolute -inset-3 rotate-2 rounded-[2rem] bg-gradient-to-br from-red-600 to-orange-500 opacity-90" />
      <form
        onSubmit={submit}
        className="relative rounded-3xl bg-white p-6 text-slate-900 shadow-2xl shadow-black/40 sm:p-8"
      >
        <div className="flex items-start justify-between gap-4">
          <div>
            <h2 className="text-2xl font-extrabold tracking-tight">Get a Free Quote</h2>
            <p className="mt-1 text-sm text-slate-500">Upfront pricing. No obligation.</p>
          </div>
          <span className="inline-flex items-center gap-1 rounded-full bg-emerald-50 px-3 py-1 text-xs font-bold text-emerald-700">
            <Clock className="h-3.5 w-3.5" />
            Replies in 60s
          </span>
        </div>

        <div className="mt-6 space-y-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <label className="block">
              <span className="mb-1.5 block text-xs font-semibold uppercase tracking-wide text-slate-500">Name</span>
              <input className={input} placeholder="Your name" autoComplete="name" />
            </label>
            <label className="block">
              <span className="mb-1.5 block text-xs font-semibold uppercase tracking-wide text-slate-500">Phone</span>
              <input className={input} placeholder="+91 98XXX XXXXX" type="tel" autoComplete="tel" />
            </label>
          </div>
          <label className="block">
            <span className="mb-1.5 block text-xs font-semibold uppercase tracking-wide text-slate-500">Service</span>
            <div className="relative">
              <select className={`${input} appearance-none pr-10`} defaultValue="">
                <option value="" disabled>
                  What do you need help with?
                </option>
                <option>Emergency leak / burst pipe</option>
                <option>Blocked drain</option>
                <option>Water heater / geyser</option>
                <option>Roof leak repair</option>
                <option>Roof inspection</option>
                <option>New roof / re-roofing</option>
              </select>
              <ChevronDown className="pointer-events-none absolute right-3 top-1/2 h-5 w-5 -translate-y-1/2 text-slate-400" />
            </div>
          </label>
          <label className="block">
            <span className="mb-1.5 block text-xs font-semibold uppercase tracking-wide text-slate-500">Area</span>
            <input className={input} placeholder="e.g. Baner, Pune" />
          </label>
        </div>

        <button
          type="submit"
          className="mt-6 inline-flex w-full items-center justify-center gap-2 rounded-xl bg-red-600 px-6 py-4 text-base font-bold text-white shadow-lg shadow-red-600/30 transition hover:bg-red-500"
        >
          <PhoneCall className="h-5 w-5" />
          Get My Free Quote
        </button>
        <p className="mt-3 text-center text-xs text-slate-500">
          Opens a live call with our AI dispatcher, who books your visit by voice.
        </p>

        <div className="mt-6 grid grid-cols-3 gap-2 border-t border-slate-100 pt-5 text-center">
          {[
            [ShieldCheck, "Licensed"],
            [BadgeCheck, "Insured"],
            [Award, "Warranty"],
          ].map(([Icon, label]) => {
            const I = Icon as typeof ShieldCheck;
            return (
              <div key={label as string} className="flex flex-col items-center gap-1 text-xs font-semibold text-slate-600">
                <I className="h-5 w-5 text-slate-900" />
                {label as string}
              </div>
            );
          })}
        </div>
      </form>
    </div>
  );
}

function TrustBar() {
  const stats = [
    { icon: Clock, value: "24/7", label: "AI dispatch, every day" },
    { icon: MapPin, value: "40 km", label: "Service radius" },
    { icon: Droplets, value: "Plumbing", label: "Leaks, drains, geysers" },
    { icon: House, value: "Roofing", label: "Repairs & re-roofs" },
  ];
  return (
    <div className="border-b border-slate-200 bg-white">
      <div className="mx-auto grid max-w-7xl grid-cols-2 gap-6 px-4 py-8 sm:px-6 lg:grid-cols-4 lg:px-8">
        {stats.map(({ icon: Icon, value, label }) => (
          <div key={label} className="flex items-center gap-4">
            <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-slate-900 text-white">
              <Icon className="h-5 w-5" />
            </span>
            <div>
              <p className="text-xl font-extrabold text-slate-900">{value}</p>
              <p className="text-sm text-slate-500">{label}</p>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Section 2: Trust & Testimonials
// ─────────────────────────────────────────────────────────────────────────────
function Testimonials({ onCall }: { onCall: () => void }) {
  return (
    <section id="reviews" className="scroll-mt-24 bg-slate-50 py-20 md:py-28">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <div className="flex flex-col items-start justify-between gap-8 md:flex-row md:items-end">
          <div className="max-w-2xl">
            <SectionLabel>Trust &amp; Testimonials</SectionLabel>
            <h2 className="mt-3 text-3xl font-extrabold tracking-tight text-slate-900 sm:text-4xl">
              Genuine Local Service
            </h2>
            <p className="mt-4 text-lg text-slate-600">
              Real homeowners, real repairs. We are a local team, so our reputation lives on your street.
            </p>
          </div>
          <div className="flex items-center gap-4 rounded-2xl border border-slate-200 bg-white px-5 py-4 shadow-sm">
            <GoogleG className="h-9 w-9" />
            <div>
              <div className="flex items-center gap-2">
                <span className="text-2xl font-extrabold text-slate-900">4.9</span>
                <Stars />
              </div>
              <p className="text-xs text-slate-500">Google Reviews rating</p>
            </div>
          </div>
        </div>

        <div className="mt-12 grid gap-6 md:grid-cols-2">
          {TESTIMONIALS.map((t) => (
            <figure
              key={t.name}
              className="flex flex-col rounded-3xl border border-slate-200 bg-white p-7 shadow-sm transition hover:-translate-y-1 hover:shadow-xl"
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <span className="flex h-11 w-11 items-center justify-center rounded-full bg-gradient-to-br from-slate-700 to-slate-900 text-sm font-bold text-white">
                    {t.initials}
                  </span>
                  <div>
                    <p className="font-semibold text-slate-900">{t.name}</p>
                    <p className="text-xs text-slate-500">{t.area}</p>
                  </div>
                </div>
                <GoogleG />
              </div>
              <div className="mt-4 flex items-center gap-3">
                <Stars />
                <span className="text-xs text-slate-400">{t.when}</span>
              </div>
              <blockquote className="mt-4 flex-1 leading-relaxed text-slate-700">&ldquo;{t.text}&rdquo;</blockquote>
              <p className="mt-5 inline-flex items-center gap-1.5 text-xs font-semibold text-emerald-700">
                <CircleCheck className="h-4 w-4" />
                Verified customer
              </p>
            </figure>
          ))}
        </div>

        <div className="mt-12 flex flex-col items-center gap-3 text-center">
          <CallButton onClick={onCall}>Talk to Our AI Dispatcher Now</CallButton>
          <p className="text-sm text-slate-500">Join hundreds of happy Pune homeowners.</p>
        </div>
      </div>
    </section>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Section 3: The 6-Step Process
// ─────────────────────────────────────────────────────────────────────────────
function Process({ onCall }: { onCall: () => void }) {
  return (
    <section id="process" className="scroll-mt-24 bg-white py-20 md:py-28">
      <div className="mx-auto grid max-w-7xl gap-12 px-4 sm:px-6 lg:grid-cols-[1fr_1.4fr] lg:gap-20 lg:px-8">
        <div className="lg:sticky lg:top-32 lg:self-start">
          <SectionLabel>How it works</SectionLabel>
          <h2 className="mt-3 text-3xl font-extrabold tracking-tight text-slate-900 sm:text-4xl">
            Our 6-Step Process
          </h2>
          <p className="mt-4 text-lg text-slate-600">
            From your first word to the final sweep, every job follows the same proven path. Step two is where we
            are different: an AI dispatcher that never sleeps and never puts you on hold.
          </p>
          <div className="mt-8 rounded-2xl bg-slate-900 p-6 text-white">
            <p className="flex items-center gap-2 font-semibold">
              <Bot className="h-5 w-5 text-red-400" />
              Try step 2 live
            </p>
            <p className="mt-2 text-sm text-slate-400">
              Describe a leak, ask for a roof quote, or just ask about our hours.
            </p>
            <CallButton onClick={onCall} className="mt-5 w-full">
              Start a Call
            </CallButton>
          </div>
        </div>

        <ol className="relative">
          {/* Vertical rail */}
          <span aria-hidden className="absolute bottom-8 left-7 top-8 w-px bg-gradient-to-b from-red-600 via-slate-200 to-slate-200" />
          {STEPS.map((step, i) => {
            const Icon = step.icon;
            return (
              <li key={step.title} className="relative flex gap-6 pb-10 last:pb-0">
                <span
                  className={`relative z-10 flex h-14 w-14 shrink-0 items-center justify-center rounded-2xl shadow-lg ${
                    step.highlight ? "bg-red-600 text-white shadow-red-600/30" : "bg-slate-900 text-white shadow-slate-900/20"
                  }`}
                >
                  <Icon className="h-6 w-6" />
                </span>
                <div
                  className={`flex-1 rounded-2xl border p-5 transition ${
                    step.highlight ? "border-red-200 bg-red-50/60" : "border-slate-200 bg-white hover:border-slate-300"
                  }`}
                >
                  <p className="text-xs font-bold uppercase tracking-widest text-slate-400">Step {i + 1}</p>
                  <h3 className="mt-1 flex flex-wrap items-center gap-2 text-lg font-bold text-slate-900">
                    {step.title}
                    {step.highlight && (
                      <span className="rounded-full bg-red-600 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-white">
                        Live AI
                      </span>
                    )}
                  </h3>
                  <p className="mt-1.5 text-slate-600">{step.text}</p>
                </div>
              </li>
            );
          })}
        </ol>
      </div>
    </section>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Section 4: Why Choose Us (FAQ)
// ─────────────────────────────────────────────────────────────────────────────
function WhyChooseUs({ onCall }: { onCall: () => void }) {
  const [openFaq, setOpenFaq] = useState<number | null>(0);
  return (
    <section id="why-us" className="relative scroll-mt-24 overflow-hidden bg-slate-900 py-20 text-white md:py-28">
      <div aria-hidden className="pointer-events-none absolute -right-40 top-0 h-[30rem] w-[30rem] rounded-full bg-red-600/15 blur-[120px]" />
      <div className="relative mx-auto grid max-w-7xl gap-14 px-4 sm:px-6 lg:grid-cols-2 lg:gap-20 lg:px-8">
        <div>
          <SectionLabel dark>Why choose us</SectionLabel>
          <h2 className="mt-3 text-3xl font-extrabold tracking-tight sm:text-4xl">The Summit Promise</h2>
          <p className="mt-4 text-lg text-slate-300">
            Four commitments on every job, big or small. If we fall short on any of them, tell us and we will make
            it right.
          </p>

          <ul className="mt-10 space-y-4">
            {PROMISES.map((p) => (
              <li key={p.title} className="flex gap-4 rounded-2xl border border-white/10 bg-white/[0.04] p-5">
                <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-red-600">
                  <Check className="h-5 w-5" strokeWidth={3} />
                </span>
                <div>
                  <p className="font-bold">{p.title}</p>
                  <p className="mt-0.5 text-sm text-slate-400">{p.text}</p>
                </div>
              </li>
            ))}
          </ul>

          <CallButton onClick={onCall} className="mt-10">
            Call 24/7 AI Dispatch
          </CallButton>
        </div>

        <div id="faq" className="scroll-mt-24">
          <h3 className="text-xl font-bold">Frequently asked questions</h3>
          <p className="mt-2 text-sm text-slate-400">Our AI receptionist answers all of these on a call, too.</p>
          <div className="mt-8 divide-y divide-white/10 rounded-2xl border border-white/10 bg-white/[0.03]">
            {FAQS.map((f, i) => {
              const open = openFaq === i;
              return (
                <div key={f.q}>
                  <button
                    type="button"
                    onClick={() => setOpenFaq(open ? null : i)}
                    aria-expanded={open}
                    className="flex w-full items-center justify-between gap-4 px-6 py-5 text-left font-semibold transition hover:bg-white/[0.03]"
                  >
                    {f.q}
                    <ChevronDown className={`h-5 w-5 shrink-0 text-red-400 transition ${open ? "rotate-180" : ""}`} />
                  </button>
                  <div className={`grid transition-all duration-300 ${open ? "grid-rows-[1fr]" : "grid-rows-[0fr]"}`}>
                    <div className="overflow-hidden">
                      <p className="px-6 pb-5 text-slate-400">{f.a}</p>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
          <div className="mt-6 flex flex-col items-start gap-3 rounded-2xl border border-red-500/30 bg-red-600/10 p-5 sm:flex-row sm:items-center sm:justify-between">
            <p className="text-sm text-slate-200">Still have a question? Ask it out loud.</p>
            <CallButton onClick={onCall} size="sm">
              Ask Our AI
            </CallButton>
          </div>
        </div>
      </div>
    </section>
  );
}

function FinalCta({ onCall }: { onCall: () => void }) {
  return (
    <section className="bg-white py-20">
      <div className="mx-auto max-w-5xl px-4 sm:px-6 lg:px-8">
        <div className="relative overflow-hidden rounded-[2rem] bg-gradient-to-br from-red-600 to-red-700 px-6 py-14 text-center text-white shadow-2xl shadow-red-600/30 sm:px-12">
          <div aria-hidden className="absolute inset-0 bg-[radial-gradient(circle_at_top_right,rgba(255,255,255,0.25),transparent_55%)]" />
          <div className="relative">
            <h2 className="text-3xl font-extrabold tracking-tight sm:text-4xl">Water coming through the ceiling?</h2>
            <p className="mx-auto mt-4 max-w-xl text-lg text-red-100">
              Don&apos;t wait for office hours. Our AI dispatcher triages your emergency and sends a technician now.
            </p>
            <button
              type="button"
              onClick={onCall}
              className="mt-8 inline-flex items-center gap-2.5 rounded-full bg-white px-8 py-4 text-lg font-bold text-red-600 shadow-xl transition hover:-translate-y-0.5 hover:bg-red-50"
            >
              <PhoneCall className="h-5 w-5" />
              Call 24/7 AI Dispatch
            </button>
          </div>
        </div>
      </div>
    </section>
  );
}

function Footer({ onCall }: { onCall: () => void }) {
  return (
    <footer className="bg-slate-950 pb-28 pt-14 text-slate-400 md:pb-14">
      <div className="mx-auto flex max-w-7xl flex-col gap-10 px-4 sm:px-6 md:flex-row md:items-start md:justify-between lg:px-8">
        <div className="max-w-sm">
          <p className="text-lg font-extrabold text-white">SUMMIT Roofing &amp; Plumbing</p>
          <p className="mt-3 text-sm">
            Licensed and insured plumbing and roofing for homes and light-commercial properties across the Pune
            region, Maharashtra.
          </p>
        </div>
        <div className="text-sm">
          <p className="font-semibold text-white">Hours</p>
          <p className="mt-2">Office: Mon to Sat, 8am to 6pm</p>
          <p>Emergency dispatch: 24/7</p>
        </div>
        <CallButton onClick={onCall} size="sm" className="self-start">
          Call 24/7 AI Dispatch
        </CallButton>
      </div>
      <p className="mx-auto mt-12 max-w-7xl border-t border-white/5 px-4 pt-6 text-xs text-slate-600 sm:px-6 lg:px-8">
        Concept site built for the VIT Bhopal project exhibition. Business details and reviews are illustrative.
        Voice powered by LiveKit WebRTC agents.
      </p>
    </footer>
  );
}
