import "./Footer.css";

function Footer() {
  return (
    <footer className="footer">

      {/* =========================
          Footer Main
      ========================= */}

      <div className="footer-container">

        {/* =========================
            Left Side - Contact Info
        ========================= */}

        <div className="footer-contact">

          

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


        {/* =========================
            Right Side - Social Media
        ========================= */}

        <div className="footer-social">

          <h2>Social Media</h2>

          <div className="social-icons">

            <a
              href="#"
              aria-label="Facebook"
            >
              <img
                src="/images/facebook.png"
                alt="Facebook"
              />
            </a>

            <a
              href="#"
              aria-label="Instagram"
            >
              <img
                src="/images/instagram.png"
                alt="Instagram"
              />
            </a>

            <a
              href="#"
              aria-label="Twitter"
            >
              <img
                src="/images/twitter.png"
                alt="Twitter"
              />
            </a>

          </div>

        </div>

      </div>


      {/* =========================
          Copyright
      ========================= */}

      <div className="copyright">

        © 2026 Comfort Zone Furniture | All Rights Reserved.

      </div>

    </footer>
  );
}

export default Footer;