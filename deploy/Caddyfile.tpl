# Portal de la Heladería Leche de Cabra: https://__PUBLIC_IP__/portal_heladeria
# Let's Encrypt emite certificados para direcciones IP solo con el perfil "shortlived"
# (válidos 160 horas). Caddy los renueva solo; requiere los puertos 80 y 443 abiertos.
{
	# Al entrar por IP, los clientes no envían SNI: sin esto Caddy no sabe qué
	# certificado entregar y responde "tlsv1 alert internal error".
	default_sni __PUBLIC_IP__
	email __ACME_EMAIL__
}

(portal_routes) {
	encode zstd gzip
	redir / /portal_heladeria/ 302
	redir /portal_heladeria /portal_heladeria/ 308

	# API (FastAPI en 127.0.0.1:8000)
	handle /portal_heladeria/api/* {
		uri strip_prefix /portal_heladeria
		reverse_proxy 127.0.0.1:8000
	}

	# Frontend estático (export de Next.js)
	handle /portal_heladeria/* {
		uri strip_prefix /portal_heladeria
		root * /opt/xyz/portal/web
		try_files {path} {path}/index.html
		file_server
	}

	handle_errors 404 {
		root * /opt/xyz/portal/web
		rewrite * /404.html
		file_server
	}

	handle {
		respond "Not found" 404
	}

	header {
		Strict-Transport-Security "max-age=31536000"
		X-Content-Type-Options "nosniff"
		X-Frame-Options "DENY"
		Referrer-Policy "same-origin"
		Permissions-Policy "camera=(), microphone=(), geolocation=()"
		Content-Security-Policy "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
		-Server
	}
	log {
		output file /var/log/caddy/portal.log
	}
}

https://__PUBLIC_IP__ {
	tls {
		issuer acme {
			profile shortlived
		}
	}
	import portal_routes
}

http://__PUBLIC_IP__ {
	redir https://__PUBLIC_IP__{uri} 308
}
