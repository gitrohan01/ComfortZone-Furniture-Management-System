import "../css/About.css";

export default function About() {
  return (
    <section className="about">

      <div className="about-container">

        {/* IMAGE */}
        <div className="about-image">
          <img
            src="https://images.unsplash.com/photo-1505693416388-ac5ce068fe85?w=900"
            alt="Comfort Zone Furniture"
          />
        </div>

        {/* CONTENT */}
        <div className="about-content">

          <h1>About Us</h1>

          <h4>Welcome to Comfort Zone Furniture</h4>

          <p>
            <strong>Comfort Zone Furniture</strong> is a trusted online
            furniture shopping destination established in{" "}
            <strong>2015</strong>. We specialize in premium-quality furniture
            designed to bring comfort, elegance, and style to every home.
          </p>

          <p>
            Founded by <strong>Mrs. Preeti Gharge</strong>, our mission is to
            provide modern, durable, and affordable furniture for every family.
            From luxurious sofas and beds to wardrobes, dining tables,
            dressing tables, and office furniture, we offer everything you
            need to create your dream home.
          </p>

          <p>
            At Comfort Zone Furniture, customer satisfaction is our highest
            priority. We combine quality craftsmanship, innovative designs,
            and exceptional service to ensure every purchase is a delightful
            experience.
          </p>

          <div className="about-info">

            <div className="info-box">
              <h2>10+</h2>
              <span>Years Experience</span>
            </div>

            <div className="info-box">
              <h2>5000+</h2>
              <span>Happy Customers</span>
            </div>

            <div className="info-box">
              <h2>100+</h2>
              <span>Furniture Designs</span>
            </div>

          </div>

          <button className="about-btn">
            Explore Collection
          </button>

        </div>

      </div>

    </section>
  );
}