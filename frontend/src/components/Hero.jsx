import "../css/Hero.css";

export default function Hero() {
  return (
    <section className="hero">
      <div className="hero-content">

        <div className="hero-text">
          <h1>Modern Furniture For Your Dream Home</h1>

          <p>
            Premium quality furniture with modern designs to transform your
            living space.
          </p>

          <button className="hero-btn">
            Explore Collection
          </button>
        </div>

        <div className="hero-image">
          <img
            src="https://images.unsplash.com/photo-1505693416388-ac5ce068fe85?w=900"
            alt="Modern Furniture"
          />
        </div>

      </div>
    </section>
  );
}
