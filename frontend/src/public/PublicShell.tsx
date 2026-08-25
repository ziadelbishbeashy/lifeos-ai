import { useEffect, type ReactNode } from "react";

export function PublicShell({children}:{children:ReactNode}){
  useEffect(()=>{document.body.className="public-body";document.documentElement.removeAttribute("data-theme")},[]);
  return <><nav className="public-navbar"><a href="/" className="public-brand"><span className="public-brand-icon">L</span><span><strong>LifeOS AI</strong><small>Execution Intelligence</small></span></a><div className="public-navigation"><a href="/#features">Features</a><a href="/#workflow">How It Works</a><a href="/login" className="navigation-login">Log In</a><a href="/register" className="navigation-register">Get Started</a></div></nav>{children}<footer className="public-footer"><div><strong>LifeOS AI</strong><p>Turn scattered work into clear, intelligent execution.</p></div><span>Personal Execution Intelligence Workspace</span></footer></>
}
