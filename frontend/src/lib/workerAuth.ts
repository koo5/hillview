let tokenPromise;

async function getValidToken()
{
	if (tokenPromise) {
		return tokenPromise;
	}

	tokenPromise = new Promise<string | null>(async (resolve) => {
		
	});

}
