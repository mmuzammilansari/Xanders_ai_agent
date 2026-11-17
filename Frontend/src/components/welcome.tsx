"use client";

import { ArrowUpRight, Asterisk, BadgePercent, CircleDollarSign, LifeBuoy, Utensils } from "lucide-react";

const suggestions = [
  { icon: Utensils, title: "Browse the menu", detail: "Explore dishes and prices", query: "What's on the menu?" },
  { icon: CircleDollarSign, title: "Check a price", detail: "Ask about a menu favorite", query: "How much is a Zinger Burger?" },
  { icon: BadgePercent, title: "Today's deal", detail: "See the current discount", query: "What's today's discount?" },
  { icon: LifeBuoy, title: "Order support", detail: "Get help with a concern", query: "I'd like to report a problem with my order." },
];

export function Welcome({ onPrompt, disabled }: { onPrompt: (query: string) => void; disabled: boolean }) {
  return <div className="welcome" data-enter>
    <div className="welcome-symbol"><Asterisk size={48} strokeWidth={1.15} /></div>
    <p className="eyebrow">Welcome to Xander’s</p>
    <h1>How can we<br /><em>help today?</em></h1>
    <p className="welcome-description">Choose a quick start or ask us anything about the menu, prices, offers, or your order.</p>
    <div className="suggestions">{suggestions.map(({ icon: Icon, title, detail, query }) =>
      <button key={title} onClick={() => onPrompt(query)} disabled={disabled} className="suggestion" aria-label={`Start a conversation: ${title}`}>
        <span className="suggestion-icon"><Icon size={19} strokeWidth={1.8} /></span>
        <span><strong>{title}</strong><small>{detail}</small></span>
        <ArrowUpRight className="suggestion-arrow" size={17} />
      </button>)}</div>
  </div>;
}
