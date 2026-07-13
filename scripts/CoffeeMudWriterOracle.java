import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

import com.planet_ink.coffee_mud.Items.interfaces.Item;
import com.planet_ink.coffee_mud.MOBS.interfaces.MOB;
import com.planet_ink.coffee_mud.core.CMClass;
import com.planet_ink.coffee_mud.core.CMFile;
import com.planet_ink.coffee_mud.core.CMLib;
import com.planet_ink.coffee_mud.core.CMProps;
import com.planet_ink.coffee_mud.core.CMSecurity;
import com.planet_ink.coffee_mud.core.Directions;
import com.planet_ink.coffee_mud.core.Log;
import com.planet_ink.coffee_mud.core.Resources;
import com.planet_ink.coffee_mud.core.database.DBConnector;
import com.planet_ink.coffee_mud.core.database.DBInterface;
import com.planet_ink.coffee_mud.core.threads.ServiceEngine;
import com.planet_ink.coffee_mud.Libraries.interfaces.DatabaseEngine.AckRecord;

public final class CoffeeMudWriterOracle
{
	public static final class EmptyDatabase extends DBInterface
	{
		EmptyDatabase()
		{
			super(new DBConnector(), Collections.emptySet(), null);
		}

		@Override
		public CMFile.CMVFSDir DBReadVFSDirectory()
		{
			return new CMFile.CMVFSDir(null, "");
		}

		@Override
		public List<AckRecord> DBReadAbilities()
		{
			return Collections.emptyList();
		}

		@Override
		public List<AckRecord> DBReadCommands()
		{
			return Collections.emptyList();
		}

		@Override
		public List<AckRecord> DBReadRaces()
		{
			return Collections.emptyList();
		}

		@Override
		public List<AckRecord> DBReadClasses()
		{
			return Collections.emptyList();
		}
	}

	private CoffeeMudWriterOracle()
	{
	}

	private static void initializeCoffeeMud()
	{
		CMLib.initialize();
		CMClass.initialize();
		Resources.initialize();
		CMSecurity.instance();
		final Log log = Log.instance();
		log.configureLog(Log.Type.error, "ON");
		final CMProps properties = CMProps.loadPropPage("//coffeemud.ini");
		if((properties == null) || (!properties.isLoaded()))
			throw new IllegalStateException("Unable to load coffeemud.ini");
		properties.resetSystemVars();
		CMProps.setState(CMProps.HostState.BOOTING);
		Directions.instance();
		CMLib.registerLibrary(new EmptyDatabase());
		CMLib.registerLibrary(new ServiceEngine());
		if(!CMClass.loadAllCoffeeMudClasses(properties))
			throw new IllegalStateException("Unable to load CoffeeMud classes");
		CMClass.instance().intializeClasses();
	}

	private static void validate(final String argument) throws Exception
	{
		final int separator = argument.indexOf(':');
		if(separator <= 0)
			throw new IllegalArgumentException("Expected LABEL:PATH, got " + argument);
		final String label = argument.substring(0, separator);
		final Path path = Path.of(argument.substring(separator + 1));
		System.out.println("BEGIN\t" + label + "\t" + path);
		final String xml = Files.readString(path, StandardCharsets.ISO_8859_1);
		final String error;
		final int count;
		if(xml.stripLeading().startsWith("<MOBS>"))
		{
			final List<MOB> mobs = new ArrayList<MOB>();
			error = CMLib.coffeeMaker().addMOBsFromXML(xml, mobs, null);
			count = mobs.size();
		}
		else
		if(xml.stripLeading().startsWith("<ITEMS>"))
		{
			final List<Item> items = new ArrayList<Item>();
			error = CMLib.coffeeMaker().addItemsFromXML(xml, items, null);
			count = items.size();
		}
		else
			throw new IllegalArgumentException("Unsupported oracle document: " + path);
		if((error != null) && (!error.isEmpty()))
			throw new IllegalStateException(path + ": " + error);
		if(count == 0)
			throw new IllegalStateException(path + ": loader returned no records");
		System.out.println("RESULT\t" + label + "\t" + path + "\t" + count);
		System.out.println("END\t" + label + "\t" + path);
	}

	private static void run(final String[] arguments) throws Exception
	{
		initializeCoffeeMud();
		for(final String argument : arguments)
			validate(argument);
	}

	public static void main(final String[] arguments) throws Exception
	{
		if(arguments.length == 0)
			throw new IllegalArgumentException("Supply at least one LABEL:PATH .cmare argument");
		final Throwable[] failure = new Throwable[1];
		final ThreadGroup group = new ThreadGroup("0");
		final Thread oracle = new Thread(group, () -> {
			try
			{
				run(arguments);
			}
			catch(final Throwable error)
			{
				failure[0] = error;
			}
		}, "CoffeeMudWriterOracle");
		oracle.start();
		oracle.join();
		if(failure[0] != null)
			throw new RuntimeException(failure[0]);
	}
}
