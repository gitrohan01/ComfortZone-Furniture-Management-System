import { Link } from "react-router-dom";
import "../css/Home.css";
// import Footer from "./Footer";

function Home() {
  return (
    <>
      <div className="home-page">

        <main className="home-content">

          <section className="hero">

            <div className="hero-text">

              <p className="welcome-text">
                WELCOME TO COMFORT ZONE
              </p>

              <h1>
                Modern Furniture
                <br />
                For Your
                <span>{" "}Dream Home</span>
              </h1>

              <p className="hero-description">
                Discover premium quality furniture
                with elegant designs and exceptional
                comfort to transform your home into
                a beautiful living space.
              </p>

              <div className="home-buttons">

                <Link
                  to="/beds"
                  className="explore-btn"
                >
                  Explore Collection
                </Link>

                <Link
                  to="/login"
                  className="home-login-btn"
                >
                  Login
                </Link>

              </div>

            </div>

            <div className="hero-image">

              <img
                src="https://images.unsplash.com/photo-1505693416388-ac5ce068fe85?w=1200"
                alt="Modern Furniture"
              />

            </div>

          </section>

        </main>

      </div>

      {/* Footer */}
      {/* <Footer /> */}
    </>
  );
}

export default Home;