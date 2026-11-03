import "../css/Contactus.css";


export default function Contact() {
  return (
    <div className="contact-page">

      {/* =========================
          Contact Main Section
      ========================= */}

      <div className="contact-main">

        {/* LEFT SIDE - MAP */}
        <div className="map-section">

          <h2>Our Location</h2>

          <iframe
            title="Comfort Zone Furniture"
            src="https://www.google.com/maps?q=Nariman+Hall,+Satara+Rahimatpur+Road,+Old+MIDC,+Satara&output=embed"
            loading="lazy"
          ></iframe>

        </div>


        {/* RIGHT SIDE - CONTACT DETAILS */}
        <div className="contact-info">

          <div className="footer-box">

            <h2>Contact Us</h2>

            <p>
              <strong>Comfort Zone Furniture</strong>
            </p>

            <p>
              Nariman Hall <br />
              Satara Rahimatpur Road <br />
              Old MIDC <br />
              Satara - 415004
            </p>

            <p>📞 +91 9876543210</p>

            <p>📧 comfortzone@gmail.com</p>

          </div>


          {/* SOCIAL MEDIA */}

          {/* <div className="footer-box">

            <h2>Social Media</h2>

            <div className="social-icons">

              <a href="#">📘</a>

              <a href="#">📷</a>

              <a href="#">🐦</a>

              <a href="#">💼</a>

            </div>

          </div> */}

        </div>

      </div>


    </div>
  );
}