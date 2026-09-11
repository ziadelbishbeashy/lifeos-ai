import { useEffect, type ReactNode } from "react";
import { BrandMark } from "../components/VSpaceUi";

export function PublicShell({children}:{children:ReactNode}){
  useEffect(()=>{document.body.className="public-body";document.documentElement.removeAttribute("data-theme")},[]);
  return <><nav className="public-navbar"><a href="/" className="public-brand"><span className="public-brand-icon"><BrandMark/></span><span><strong>V-SPACE AI</strong><small>Virtual Smart Space</small></span></a><div className="public-navigation"><a href="/#features">Features</a><a href="/#workflow">How It Works</a><a href="/login" className="navigation-login">Log In</a><a href="/register" className="navigation-register">Get Started</a></div></nav>{children}<footer className="public-footer"><div><strong>V-SPACE AI</strong><p>Turn scattered work into clear, intelligent execution.</p></div><span>Personal Execution Intelligence Workspace</span></footer></>
}
