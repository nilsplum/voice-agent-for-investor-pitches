/** Every path the router does not know. The start page sends a logged-in user on to their area. */
import { Link } from "react-router";

export function NotFound() {
  return (
    <section className="card">
      <h1>Diese Seite gibt es nicht.</h1>
      <Link to="/">Zur Startseite</Link>
    </section>
  );
}
