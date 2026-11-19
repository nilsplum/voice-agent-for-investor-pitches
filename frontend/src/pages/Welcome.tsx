/** The public welcome page: the welcome letter and the two ways in, signup and login. */
import { Mic } from "lucide-react";
import { Link } from "react-router";

export function Welcome() {
  return (
    <section className="card welcome">
      <Mic className="welcome-icon" size={40} aria-hidden />
      <h1>Willkommen beim Voice Agent for Investor Pitches</h1>
      <p>
        Hier führen Sie Ihr Erstgespräch mit uns als Investor: ein Sprachgespräch von etwa 10 bis 15 Minuten
        mit einem KI-Agenten. Er fragt nach Ihrem Startup und schreibt Ihre Antworten für unser Investmentteam
        auf. Sie brauchen den Zugangscode, den Ihnen das Team geschickt hat, einen ruhigen Ort und ein Mikrofon.
      </p>
      <div className="actions">
        <Link to="/signup" className="button button-primary">Registrieren</Link>
        <Link to="/login" className="button">Anmelden</Link>
      </div>
    </section>
  );
}
